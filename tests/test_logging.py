import logging

import pytest

import logging_config
from tests.conftest import client_error, text_reply, tool_reply


@pytest.fixture
def fresh_root_logger(tmp_path, monkeypatch):
    """Detach the app's handlers so setup_logging can be exercised in isolation, then restore them."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    for handler in saved_handlers:
        if getattr(handler, "_app_handler", False):
            root.removeHandler(handler)
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    yield root, tmp_path / "logs"
    for handler in root.handlers[:]:
        if getattr(handler, "_app_handler", False):
            root.removeHandler(handler)
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def app_handlers(root):
    return [h for h in root.handlers if getattr(h, "_app_handler", False)]


def test_setup_creates_log_file_with_format(fresh_root_logger):
    root, log_dir = fresh_root_logger
    logging_config.setup_logging()
    logging.getLogger("main").info("hello from test")
    for handler in app_handlers(root):
        handler.flush()

    line = (log_dir / "app.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "INFO" in line and "main: hello from test" in line
    assert line[:4].isdigit()


def test_setup_is_idempotent(fresh_root_logger):
    root, _ = fresh_root_logger
    logging_config.setup_logging()
    logging_config.setup_logging()
    assert len(app_handlers(root)) == 2


def test_log_level_from_env(fresh_root_logger, monkeypatch):
    root, _ = fresh_root_logger
    monkeypatch.setenv("LOG_LEVEL", "warning")
    logging_config.setup_logging()
    assert root.level == logging.WARNING


def test_noisy_libraries_quieted(fresh_root_logger):
    logging_config.setup_logging()
    assert logging.getLogger("botocore").level == logging.WARNING


def test_chat_logs_request_rounds_and_summary(chat, bedrock, caplog, sample_conversation_id):
    bedrock.script(tool_reply(("t1", "get_garage_rate", {"garage_id": "GAR-02"})), text_reply("$8/hour."))
    with caplog.at_level(logging.INFO):
        chat("Rate at GAR-02?")

    text = caplog.text
    assert f"Chat request for conversation {sample_conversation_id}" in text
    assert "Retrieved 1 documents" in text
    assert "Model round 1" in text and "stop_reason=tool_use" in text
    assert "Model round 2" in text and "stop_reason=end_turn" in text
    assert "Calling MCP tool get_garage_rate" in text
    assert "tool_calls=[{'name': 'get_garage_rate'" in text


def test_long_messages_are_truncated_in_logs(chat, bedrock, caplog):
    bedrock.script(text_reply("ok"))
    with caplog.at_level(logging.INFO, logger="main"):
        chat("x" * 1000)
    request_line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("Chat request"))
    assert "x" * 200 in request_line
    assert "x" * 201 not in request_line


def test_aws_failures_logged_with_traceback(chat, kb, caplog):
    kb.error = client_error("Retrieve")
    with caplog.at_level(logging.ERROR, logger="main"):
        chat("Hi")
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "Knowledge Base retrieval failed" in record.getMessage()
    assert record.exc_info is not None
