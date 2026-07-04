"""Demonstrate expected failure modes against Binance Futures Testnet."""

from __future__ import annotations

import getpass
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from bot.client import BinanceFuturesClient
from bot.exceptions import BinanceAPIError, NetworkError, ValidationError
from bot.logging_config import SecretRedactionFilter
from bot.orders import OrderService


def _configure_file_only_logging(redacted_values: list[str]) -> logging.Logger:
    """Configure file-only logging so the console stays clean."""

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    log_path = Path(__file__).resolve().parent / "logs" / "trading_bot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(module)s | %(message)s"))
    file_handler.addFilter(SecretRedactionFilter(redacted_values))
    root_logger.addHandler(file_handler)
    root_logger.propagate = False
    return root_logger


def _load_credentials() -> tuple[str, str]:
    """Load credentials from the environment or prompt for them."""

    api_key = (os.getenv("BINANCE_API_KEY") or "").strip()
    api_secret = (os.getenv("BINANCE_API_SECRET") or "").strip()

    if not api_key:
        api_key = input("Binance API key: ").strip()
    if not api_secret:
        api_secret = getpass.getpass("Binance API secret: ").strip()
    if not api_key:
        raise ValidationError("Binance API key is required.")
    if not api_secret:
        raise ValidationError("Binance API secret is required.")
    return api_key, api_secret


def _log_expected_failure(label: str, exc: Exception) -> None:
    """Print a clean console message and store the traceback in the log file."""

    logger = logging.getLogger("demo_error_cases")
    logger.exception("%s failed as expected", label)
    print(f"{label}: {exc}")


def main() -> int:
    """Run the three demo failure scenarios."""

    load_dotenv()
    api_key, api_secret = _load_credentials()
    _configure_file_only_logging([api_key, api_secret])

    client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret)
    service = OrderService(client)

    try:
        service.place_market_order("BTCUSDT", "BUY", 0.0000001)
        print("Scenario A unexpectedly succeeded.")
        return 1
    except ValidationError as exc:
        _log_expected_failure("Scenario A - invalid quantity", exc)

    try:
        service.place_market_order("FAKEUSDT", "BUY", 0.001)
        print("Scenario B unexpectedly succeeded.")
        return 1
    except ValidationError as exc:
        _log_expected_failure("Scenario B - invalid symbol", exc)

    try:
        client.place_order(
            symbol="BTCUSDT",
            side="BUY",
            type="LIMIT",
            timeInForce="GTC",
            quantity="1000",
            price="1",
        )
        print("Scenario C unexpectedly succeeded.")
        return 1
    except BinanceAPIError as exc:
        _log_expected_failure("Scenario C - API rejection", exc)
    except NetworkError as exc:
        _log_expected_failure("Scenario C - network error", exc)

    print("Expected failure scenarios completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())