"""Tests for the new client lookup endpoints."""

from __future__ import annotations

import pytest
import requests
import responses

from bot.client import BinanceFuturesClient


@pytest.fixture()
def client() -> BinanceFuturesClient:
    return BinanceFuturesClient("test-key", "test-secret")


@responses.activate()
def test_get_order_status_requests_signed_endpoint(client: BinanceFuturesClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bot.client.time.time", lambda: 1_700_000_000.0)

    responses.add(
        responses.GET,
        f"{client.base_url}/fapi/v1/order",
        json={"orderId": 99, "status": "FILLED", "symbol": "BTCUSDT", "executedQty": "0.001"},
        status=200,
    )

    payload = client.get_order_status("BTCUSDT", 99)

    assert payload["orderId"] == 99
    assert payload["status"] == "FILLED"
    assert len(responses.calls) == 1


@responses.activate()
def test_get_order_book_depth_returns_payload(client: BinanceFuturesClient) -> None:
    responses.add(
        responses.GET,
        f"{client.base_url}/fapi/v1/depth",
        json={"lastUpdateId": 1, "bids": [["64999.9", "2.5"]], "asks": [["65000.1", "1.2"]]},
        status=200,
    )

    payload = client.get_order_book_depth("BTCUSDT")

    assert payload["lastUpdateId"] == 1
    assert payload["bids"][0][0] == "64999.9"
