import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(filename: str = "app.log") -> None:
    root = logging.getLogger()
    # Guard against adding duplicate handlers when the app module is imported again (e.g. uvicorn --reload).
    if any(getattr(handler, "_app_handler", False) for handler in root.handlers):
        return

    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    formatter = logging.Formatter(LOG_FORMAT)

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    console_handler = logging.StreamHandler()

    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        handler._app_handler = True
        root.addHandler(handler)

    for noisy in ("botocore", "boto3", "urllib3", "httpx", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
