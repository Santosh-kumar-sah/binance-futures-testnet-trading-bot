"""Standalone diagnostics for Binance Futures order and liquidity checks."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

from bot.client import BinanceFuturesClient
from bot.exceptions import BinanceAPIError, NetworkError, ValidationError
from bot.logging_config import configure_logging
from bot.validators import validate_symbol


def build_parser() -> argparse.ArgumentParser:
    """Build the diagnostic CLI argument parser."""

    parser = argparse.ArgumentParser(description="Check Binance Futures order status and book depth")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTCUSDT")
    parser.add_argument("--order-id", dest="order_id", type=int, help="Optional Binance order ID to inspect")
    parser.add_argument("--depth-limit", dest="depth_limit", type=int, default=5, help="Order book depth levels to fetch")
    parser.add_argument("--testnet", action="store_true", default=True, help="Use Binance Futures testnet")
    parser.add_argument("--mainnet", action="store_false", dest="testnet", help=argparse.SUPPRESS)
    return parser


def _load_credentials() -> tuple[str, str]:
    """Load API credentials from environment or prompt interactively."""

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


def _print_payload(label: str, payload: dict[str, Any]) -> None:
    """Print a minimal, human-readable diagnostic block."""

    print(label)
    print("-" * len(label))
    for key, value in payload.items():
        print(f"{key:<18}: {value}")


def main(argv: list[str] | None = None) -> int:
    """Run the diagnostic checks."""

    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        api_key, api_secret = _load_credentials()
        configure_logging(redacted_values=[api_key, api_secret])
        client = BinanceFuturesClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url="https://testnet.binancefuture.com" if args.testnet else "https://fapi.binance.com",
        )

        symbol = validate_symbol(args.symbol)
        depth = client.get_order_book_depth(symbol, limit=args.depth_limit)
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])
        best_bid = bids[0] if isinstance(bids, list) and bids else ["N/A", "N/A"]
        best_ask = asks[0] if isinstance(asks, list) and asks else ["N/A", "N/A"]
        _print_payload(
            "ORDER BOOK",
            {
                "symbol": symbol,
                "best_bid": best_bid[0],
                "best_bid_qty": best_bid[1],
                "best_ask": best_ask[0],
                "best_ask_qty": best_ask[1],
            },
        )

        if args.order_id is not None:
            status = client.get_order_status(symbol, args.order_id)
            _print_payload(
                "ORDER STATUS",
                {
                    "orderId": status.get("orderId", "N/A"),
                    "status": status.get("status", "N/A"),
                    "executedQty": status.get("executedQty", "N/A"),
                    "avgPrice": status.get("avgPrice", "N/A"),
                    "updateTime": status.get("updateTime", "N/A"),
                },
            )
        return 0
    except ValidationError as exc:
        logging.getLogger(__name__).exception("Diagnostic validation failure")
        print(f"DIAGNOSTIC FAILED: {exc}")
        return 1
    except BinanceAPIError as exc:
        logging.getLogger(__name__).exception("Diagnostic Binance API failure")
        print(f"DIAGNOSTIC FAILED: {exc.message}")
        return 2
    except NetworkError as exc:
        logging.getLogger(__name__).exception("Diagnostic network failure")
        print(f"DIAGNOSTIC FAILED: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
