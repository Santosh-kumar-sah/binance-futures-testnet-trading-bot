"""Unit tests for order service validation and normalization."""

from __future__ import annotations

from typing import Any

import pytest

from bot.exceptions import ValidationError
from bot.orders import OrderService


class FakeClient:
    """Minimal client double for order service tests."""

    def __init__(self, symbol_info: dict[str, Any], response: dict[str, Any]) -> None:
        self.symbol_info = symbol_info
        self.response = response
        self.place_order_calls: list[dict[str, Any]] = []

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        return self.symbol_info

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.place_order_calls.append(kwargs)
        return self.response


def _symbol_info() -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "filters": [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
            },
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.1",
                "maxPrice": "1000000",
                "tickSize": "0.1",
            },
        ],
    }


def _order_response() -> dict[str, Any]:
    return {
        "orderId": 123,
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "abc",
        "price": "70000",
        "avgPrice": "0",
        "origQty": "0.001",
        "executedQty": "0",
        "cumQuote": "0",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "reduceOnly": False,
        "closePosition": False,
        "side": "BUY",
        "positionSide": "BOTH",
        "stopPrice": "0",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": False,
        "origType": "LIMIT",
        "updateTime": 1_700_000_000_000,
    }


def test_place_market_order_rejects_invalid_step_size() -> None:
    client = FakeClient(_symbol_info(), _order_response())
    service = OrderService(client)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="must be a multiple of stepSize"):
        service.place_market_order("BTCUSDT", "BUY", 0.0001)


def test_place_limit_order_returns_full_normalized_schema() -> None:
    client = FakeClient(_symbol_info(), _order_response())
    service = OrderService(client)  # type: ignore[arg-type]

    response = service.place_limit_order("BTCUSDT", "BUY", 0.001, 70000)

    assert response["orderId"] == 123
    assert response["clientOrderId"] == "abc"
    assert response["updateTimeUtc"] == "2023-11-14 22:13:20 UTC"
    assert client.place_order_calls


def test_place_stop_limit_order_validates_price_tick_size() -> None:
    client = FakeClient(_symbol_info(), _order_response())
    service = OrderService(client)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="must be a multiple of tickSize"):
        service.place_stop_limit_order("BTCUSDT", "BUY", 0.001, 70000.05, 69999.95)