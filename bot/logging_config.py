"""Logging configuration for the trading bot."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable


class SecretRedactionFilter(logging.Filter):
    """Redact known sensitive values from log messages."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def configure_logging(
    log_file_path: str | Path | None = None,
    *,
    redacted_values: Iterable[str] = (),
) -> logging.Logger:
    """Configure console and rotating file logging.

    Args:
        log_file_path: Optional path to the log file.
        redacted_values: Values that must not appear in log output.

    Returns:
        The configured root logger.
    """

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    if log_file_path is None:
        log_path = Path(__file__).resolve().parents[1] / "logs" / "trading_bot.log"
    else:
        log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_format = logging.Formatter("%(asctime)s | %(levelname)s | %(module)s | %(message)s")

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    file_handler.addFilter(SecretRedactionFilter(redacted_values))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    console_handler.addFilter(SecretRedactionFilter(redacted_values))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger
