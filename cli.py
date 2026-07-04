"""Command-line interface for the Binance Futures testnet trading bot."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from bot.client import BinanceFuturesClient
from bot.exceptions import BinanceAPIError, NetworkError, ValidationError
from bot.logging_config import configure_logging
from bot.orders import OrderService
from bot.validators import (
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_stop_price,
    validate_symbol,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(description="Binance Futures Testnet trading bot")
    parser.add_argument("--symbol", help="Trading symbol, e.g. BTCUSDT")
    parser.add_argument("--side", help="BUY or SELL")
    parser.add_argument("--type", dest="order_type", help="MARKET, LIMIT, or STOP_LIMIT")
    parser.add_argument("--quantity", help="Order quantity")
    parser.add_argument("--price", help="Order price for LIMIT or STOP_LIMIT")
    parser.add_argument("--stop-price", dest="stop_price", help="Stop price for STOP_LIMIT")
    parser.add_argument("--testnet", action="store_true", default=True, help="Use Binance Futures testnet")
    parser.add_argument("--mainnet", action="store_false", dest="testnet", help=argparse.SUPPRESS)
    return parser


def _prompt_if_missing(value: str | None, prompt_text: str) -> str:
    """Prompt for a value if it was not supplied on the command line."""

    if value is not None and str(value).strip():
        return str(value).strip()
    response = input(prompt_text).strip()
    if not response:
        raise ValidationError(f"{prompt_text.rstrip(': ')} is required.")
    return response


def _prompt_optional_price(value: str | None, prompt_text: str) -> str | None:
    """Prompt for an optional price value when the selected order type requires it."""

    if value is not None and str(value).strip():
        return str(value).strip()
    response = input(prompt_text).strip()
    if not response:
        return None
    return response


def _prompt_credentials(api_key: str | None, api_secret: str | None) -> tuple[str, str]:
    """Load credentials from the environment or prompt for them interactively."""

    key = (api_key or os.getenv("BINANCE_API_KEY") or "").strip()
    secret = (api_secret or os.getenv("BINANCE_API_SECRET") or "").strip()

    if not key:
        key = input("Binance API key: ").strip()
    if not secret:
        secret = getpass.getpass("Binance API secret: ").strip()
    if not key:
        raise ValidationError("Binance API key is required.")
    if not secret:
        raise ValidationError("Binance API secret is required.")
    return key, secret


def _format_order_request_block(order: dict[str, Any], testnet: bool) -> str:
    """Render the order request summary block."""

    rows = [
        ("Symbol", order["symbol"]),
        ("Side", order["side"]),
        ("Type", order["order_type"]),
        ("Quantity", order["quantity"]),
        ("Price", order.get("price", "N/A")),
        ("Stop Price", order.get("stop_price", "N/A")),
        ("Testnet", "yes" if testnet else "no"),
    ]
    width = max(len(label) for label, _ in rows)
    lines = ["ORDER REQUEST", "-" * 13]
    for label, value in rows:
        lines.append(f"{label:<{width}} : {value}")
    return "\n".join(lines)


def _format_order_response_block(response: dict[str, Any]) -> str:
    """Render the order response summary block."""

    rows = [
        ("Order ID", response.get("orderId", "N/A")),
        ("Status", response.get("status", "N/A")),
        ("Executed Qty", response.get("executedQty", "N/A")),
        ("Avg Price", response.get("avgPrice", "N/A")),
        ("Update Time (UTC)", response.get("updateTimeUtc", "N/A")),
    ]
    width = max(len(label) for label, _ in rows)
    lines = ["ORDER RESPONSE", "-" * 14]
    for label, value in rows:
        lines.append(f"{label:<{width}} : {value}")
    return "\n".join(lines)


def _format_update_time(update_time: object) -> str:
    """Convert a millisecond update time to a UTC string."""

    if update_time in (None, "", 0):
        return "N/A"
    try:
        timestamp_seconds = int(update_time) / 1000.0
        return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return "N/A"


def _build_order_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Validate CLI arguments and build the normalized order payload."""

    symbol = validate_symbol(_prompt_if_missing(args.symbol, "Symbol: "))
    side = validate_side(_prompt_if_missing(args.side, "Side (BUY/SELL): "))
    order_type = validate_order_type(_prompt_if_missing(args.order_type, "Order type (MARKET/LIMIT/STOP_LIMIT): "))
    quantity = validate_quantity(_prompt_if_missing(args.quantity, "Quantity: "))

    payload: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
    }

    if order_type in {"LIMIT", "STOP_LIMIT"}:
        price_value = _prompt_optional_price(args.price, "Price: ")
        if price_value is None:
            raise ValidationError("price is required for LIMIT and STOP_LIMIT orders.")
        payload["price"] = validate_price(price_value)

    if order_type == "STOP_LIMIT":
        stop_price_value = _prompt_optional_price(args.stop_price, "Stop price: ")
        if stop_price_value is None:
            raise ValidationError("stop_price is required for STOP_LIMIT orders.")
        payload["stop_price"] = validate_stop_price(stop_price_value)

    return payload


def _execute_order(service: OrderService, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch the requested order type to the service."""

    order_type = payload["order_type"]
    if order_type == "MARKET":
        return service.place_market_order(payload["symbol"], payload["side"], payload["quantity"])
    if order_type == "LIMIT":
        return service.place_limit_order(
            payload["symbol"],
            payload["side"],
            payload["quantity"],
            payload["price"],
        )
    if order_type == "STOP_LIMIT":
        return service.place_stop_limit_order(
            payload["symbol"],
            payload["side"],
            payload["quantity"],
            payload["price"],
            payload["stop_price"],
        )
    raise ValidationError("type must be MARKET, LIMIT, or STOP_LIMIT.")


def _prepare_console_response(response: dict[str, Any]) -> dict[str, Any]:
    """Project the service response into the console view."""

    console_response = dict(response)
    console_response["updateTimeUtc"] = _format_update_time(response.get("updateTime"))
    return console_response


def main(argv: list[str] | None = None) -> int:
    """Run the CLI application.

    Args:
        argv: Optional argument list for testing.

    Returns:
        Process exit code.
    """

    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        api_key, api_secret = _prompt_credentials(
            os.getenv("BINANCE_API_KEY"),
            os.getenv("BINANCE_API_SECRET"),
        )
        configure_logging(redacted_values=[api_key, api_secret])
        logger = logging.getLogger(__name__)
        logger.debug("CLI arguments parsed successfully.")

        order_payload = _build_order_payload(args)
        print(_format_order_request_block(order_payload, args.testnet))

        base_url = "https://testnet.binancefuture.com" if args.testnet else "https://fapi.binance.com"
        client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret, base_url=base_url)
        service = OrderService(client)
        response = _execute_order(service, order_payload)

        if order_payload["order_type"] == "MARKET" and response.get("status") != "FILLED":
            print(f"WARNING: Order accepted but not yet filled after polling. Last known status: {response.get('status', 'N/A')}")
        print()
        print(_format_order_response_block(_prepare_console_response(response)))
        return 0
    except ValidationError as exc:
        logging.getLogger(__name__).exception("Validation failed during CLI execution.")
        print(f"ORDER FAILED: {exc}")
        return 1
    except BinanceAPIError as exc:
        logging.getLogger(__name__).exception("Binance API error during CLI execution.")
        if exc.code == -2019:
            print("ORDER FAILED: Insufficient balance on Binance Futures testnet.")
        elif exc.code == -1003 or exc.status_code == 429:
            print("ORDER FAILED: Binance rate limit exceeded. Please retry after a short delay.")
        elif exc.code == -1121:
            print("ORDER FAILED: Invalid symbol not found on the exchange.")
        else:
            print(f"ORDER FAILED: {exc.message}")
        return 2
    except NetworkError as exc:
        logging.getLogger(__name__).exception("Network error during CLI execution.")
        print(f"ORDER FAILED: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
