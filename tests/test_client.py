"""Unit tests for the Binance Futures client."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from bot.client import BinanceFuturesClient
from bot.exceptions import BinanceAPIError, NetworkError


@pytest.fixture()
def client() -> BinanceFuturesClient:
    return BinanceFuturesClient("test-key", "test-secret")


@responses.activate()
def test_place_order_signs_request_and_returns_payload(client: BinanceFuturesClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bot.client.time.time", lambda: 1_700_000_000.0)

    base_url = client.base_url
    expected_query = (
        "symbol=BTCUSDT&side=BUY&type=MARKET&quantity=0.1&timestamp=1700000000000&recvWindow=5000"
    )
    expected_signature = hmac.new(
        b"test-secret",
        expected_query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    def callback(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        parsed = urlparse(request.url)
        query = parse_qs(parsed.query)
        assert request.headers["X-MBX-APIKEY"] == "test-key"
        assert query["symbol"] == ["BTCUSDT"]
        assert query["side"] == ["BUY"]
        assert query["type"] == ["MARKET"]
        assert query["quantity"] == ["0.1"]
        assert query["timestamp"] == ["1700000000000"]
        assert query["recvWindow"] == ["5000"]
        assert query["signature"] == [expected_signature]
        body = (
            '{"orderId":12345,"status":"FILLED","symbol":"BTCUSDT","side":"BUY",'
            '"type":"MARKET","executedQty":"0.1","avgPrice":"27300.1",'
            '"origQty":"0.1","price":"0"}'
        )
        return 200, {"Content-Type": "application/json"}, body

    responses.add_callback(
        responses.POST,
        f"{base_url}/fapi/v1/order",
        callback=callback,
        content_type="application/json",
    )

    payload = client.place_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.1")
    assert payload["orderId"] == 12345
    assert payload["status"] == "FILLED"


@responses.activate()
def test_get_symbol_info_returns_matching_symbol(client: BinanceFuturesClient) -> None:
    responses.add(
        responses.GET,
        f"{client.base_url}/fapi/v1/exchangeInfo",
        json={
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.001",
                            "maxQty": "1000",
                            "stepSize": "0.001",
                        },
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.01",
                            "maxPrice": "1000000",
                            "tickSize": "0.01",
                        },
                    ],
                }
            ]
        },
        status=200,
    )

    symbol_info = client.get_symbol_info("ethusdt")
    assert symbol_info["symbol"] == "ETHUSDT"


@responses.activate()
def test_get_symbol_info_uses_cache(client: BinanceFuturesClient) -> None:
    responses.add(
        responses.GET,
        f"{client.base_url}/fapi/v1/exchangeInfo",
        json={
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                        {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                    ],
                }
            ]
        },
        status=200,
    )

    first = client.get_symbol_info("BTCUSDT")
    second = client.get_symbol_info("BTCUSDT")

    assert first["symbol"] == "BTCUSDT"
    assert second["symbol"] == "BTCUSDT"
    assert len(responses.calls) == 1


@responses.activate()
def test_get_order_status_returns_payload(client: BinanceFuturesClient, monkeypatch: pytest.MonkeyPatch) -> None:
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


@responses.activate()
def test_place_order_raises_binance_api_error_on_error_response(client: BinanceFuturesClient) -> None:
    responses.add(
        responses.POST,
        f"{client.base_url}/fapi/v1/order",
        json={"code": -2019, "msg": "Margin is insufficient."},
        status=400,
    )

    with pytest.raises(BinanceAPIError) as exc_info:
        client.place_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.1")

    assert exc_info.value.code == -2019
    assert "insufficient" in exc_info.value.message.lower()


def test_send_request_raises_network_error_after_retry_exhaustion(client: BinanceFuturesClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client.session, "request", lambda *args, **kwargs: (_ for _ in ()).throw(requests.exceptions.ConnectionError("boom")))
    client.max_retries = 1

    with pytest.raises(NetworkError):
        client.place_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.1")
