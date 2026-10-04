import logging
from types import SimpleNamespace

import pytest
import requests
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT

APP_PATH = str(ROOT / "app.py")
UNAVAILABLE_MESSAGE = "Sorry, the support assistant is temporarily unavailable. Please try again in a few minutes."


def fake_response(status: int, payload):
    def json():
        if isinstance(payload, Exception):
            raise payload
        return payload

    return SimpleNamespace(ok=200 <= status < 300, status_code=status, json=json, text=str(payload))


@pytest.fixture
def backend(monkeypatch):
    """Replace the HTTP call to the chat API and record what the UI sends."""
    state = SimpleNamespace(requests=[], reply=fake_response(200, {"response": "Your session is active."}))

    def post(url, json, timeout):
        state.requests.append({"url": url, "json": json})
        if isinstance(state.reply, Exception):
            raise state.reply
        return state.reply

    monkeypatch.setattr(requests, "post", post)
    return state


def run_app():
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


def send(at, text):
    at.chat_input[0].set_value(text).run()
    return at


def chat_texts(at):
    return [(m.name, [md.value for md in m.markdown]) for m in at.chat_message]


def test_initial_state(backend):
    at = run_app()
    assert at.title[0].value == "Parking Support Chatbot"
    assert len(at.chat_message) == 0
    assert at.session_state.conversation_id


def test_sends_message_and_shows_only_response(backend):
    at = send(run_app(), "Status of SES-1002?")
    assert chat_texts(at) == [("user", ["Status of SES-1002?"]), ("assistant", ["Your session is active."])]
    assert len(at.expander) == 0 and len(at.metric) == 0
    assert backend.requests[0]["url"].endswith("/chat")
    assert backend.requests[0]["json"] == {"message": "Status of SES-1002?", "conversation_id": at.session_state.conversation_id}


def test_follow_up_uses_same_conversation_id(backend):
    at = send(send(run_app(), "First"), "Second")
    ids = {r["json"]["conversation_id"] for r in backend.requests}
    assert len(ids) == 1
    assert len(at.chat_message) == 4


def test_new_conversation_resets(backend):
    at = send(run_app(), "Hello")
    old_id = at.session_state.conversation_id
    at.sidebar.button[0].click().run()
    assert len(at.chat_message) == 0
    assert at.session_state.conversation_id != old_id


def last_reply(at):
    return at.chat_message[-1].markdown[0].value


def test_backend_unreachable_shows_friendly_message(backend, caplog):
    backend.reply = requests.exceptions.ConnectionError("refused")
    with caplog.at_level(logging.ERROR, logger="app"):
        at = send(run_app(), "Hello")
    assert last_reply(at) == UNAVAILABLE_MESSAGE
    assert len(at.error) == 0
    assert "Couldn't reach the chat backend" in caplog.text


def test_backend_error_shows_friendly_detail(backend, caplog):
    backend.reply = fake_response(502, {"detail": "Sorry, the support assistant is temporarily unavailable."})
    with caplog.at_level(logging.ERROR, logger="app"):
        at = send(run_app(), "Hello")
    assert last_reply(at) == "Sorry, the support assistant is temporarily unavailable."
    assert len(at.error) == 0
    assert "Chat backend returned 502" in caplog.text


def test_backend_non_json_error_shows_generic_message(backend):
    backend.reply = fake_response(500, ValueError("Internal Server Error"))
    assert last_reply(send(run_app(), "Hello")) == UNAVAILABLE_MESSAGE


def test_validation_error_detail_is_not_shown(backend):
    backend.reply = fake_response(422, {"detail": [{"loc": ["body", "message"], "msg": "Field required"}]})
    reply = last_reply(send(run_app(), "Hello"))
    assert reply == UNAVAILABLE_MESSAGE
    assert "Field required" not in reply


def test_sidebar_previews_messages(backend):
    backend.reply = fake_response(200, {"response": "A" * 80})
    at = send(run_app(), "Short question")
    captions = [c.value for c in at.sidebar.caption]
    assert "👤 Short question" in captions
    assert f"🤖 {'A' * 50}..." in captions
