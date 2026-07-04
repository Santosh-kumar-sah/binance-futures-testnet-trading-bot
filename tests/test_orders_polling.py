"""Tests for MARKET order polling behavior."""

from __future__ import annotations

from typing import Any

from bot.orders import OrderService


class PollingClientStub:
    """Client double for verifying MARKET polling behavior."""

    def __init__(self) -> None:
        self.status_calls: list[tuple[str, int]] = []
        self.depth_calls: list[tuple[str, int]] = []
        self.place_order_calls: list[dict[str, Any]] = []
        self.symbol_info = {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
            ],
        }
        self._status_responses = [
            {
                "orderId": 101,
                "symbol": "BTCUSDT",
                "status": "NEW",
                "clientOrderId": "init",
                "price": "0",
                "avgPrice": "0",
                "origQty": "0.001",
                "executedQty": "0.0000",
                "cumQuote": "0",
                "timeInForce": "GTC",
                "type": "MARKET",
                "reduceOnly": False,
                "closePosition": False,
                "side": "BUY",
                "positionSide": "BOTH",
                "stopPrice": "0",
                "workingType": "CONTRACT_PRICE",
                "priceProtect": False,
                "origType": "MARKET",
                "updateTime": 1_700_000_000_000,
            },
            {
                "orderId": 101,
                "symbol": "BTCUSDT",
                "status": "FILLED",
                "clientOrderId": "final",
                "price": "0",
                "avgPrice": "65000.0",
                "origQty": "0.001",
                "executedQty": "0.001",
                "cumQuote": "65",
                "timeInForce": "GTC",
                "type": "MARKET",
                "reduceOnly": False,
                "closePosition": False,
                "side": "BUY",
                "positionSide": "BOTH",
                "stopPrice": "0",
                "workingType": "CONTRACT_PRICE",
                "priceProtect": False,
                "origType": "MARKET",
                "updateTime": 1_700_000_500_000,
            },
        ]

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        return self.symbol_info

    def get_order_book_depth(self, symbol: str, limit: int = 5) -> dict[str, Any]:
        self.depth_calls.append((symbol, limit))
        return {"bids": [["64999.9", "2.5"]], "asks": [["65000.1", "1.2"]]}

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.place_order_calls.append(kwargs)
        return self._status_responses[0]

    def get_order_status(self, symbol: str, order_id: int) -> dict[str, Any]:
        self.status_calls.append((symbol, order_id))
        if len(self.status_calls) == 1:
            return self._status_responses[0]
        return self._status_responses[1]


class LimitClientStub(PollingClientStub):
    """Client double for verifying limit orders do not poll."""

    def get_order_book_depth(self, symbol: str, limit: int = 5) -> dict[str, Any]:
        raise AssertionError("Limit orders should not call depth snapshots")

    def get_order_status(self, symbol: str, order_id: int) -> dict[str, Any]:
        raise AssertionError("Limit orders should not poll status")


def test_market_order_polls_until_filled(monkeypatch: Any) -> None:
    client = PollingClientStub()
    service = OrderService(client)  # type: ignore[arg-type]
    sleep_calls: list[float] = []
    monkeypatch.setattr("bot.orders.time.sleep", lambda seconds: sleep_calls.append(seconds))

    response = service.place_market_order("BTCUSDT", "BUY", 0.001)

    assert client.depth_calls == [("BTCUSDT", 5)]
    assert client.status_calls == [("BTCUSDT", 101), ("BTCUSDT", 101)]
    assert sleep_calls == [0.5, 0.5]
    assert response["status"] == "FILLED"
    assert response["executedQty"] == "0.001"


def test_limit_order_does_not_poll_or_snapshot() -> None:
    client = LimitClientStub()
    service = OrderService(client)  # type: ignore[arg-type]

    response = service.place_limit_order("BTCUSDT", "SELL", 0.001, 70000)

    assert client.place_order_calls
    assert response["status"] == "NEW"
