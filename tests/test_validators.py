"""Unit tests for input validators."""

from __future__ import annotations

import pytest

from bot.exceptions import ValidationError
from bot.validators import (
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_stop_price,
    validate_symbol,
)


def test_validate_symbol_accepts_uppercase_usdt_symbol() -> None:
    assert validate_symbol("btcusdt") == "BTCUSDT"


@pytest.mark.parametrize(
    "symbol",
    ["BTCUSD", "BTC_USDT", "BTC/USDT", "", None],
)
def test_validate_symbol_rejects_invalid_symbols(symbol: object) -> None:
    with pytest.raises(ValidationError):
        validate_symbol(symbol)


@pytest.mark.parametrize("side, expected", [("buy", "BUY"), ("SELL", "SELL")])
def test_validate_side_normalizes_case(side: str, expected: str) -> None:
    assert validate_side(side) == expected


@pytest.mark.parametrize("side", ["hold", "", None])
def test_validate_side_rejects_invalid_values(side: object) -> None:
    with pytest.raises(ValidationError):
        validate_side(side)


@pytest.mark.parametrize(
    "order_type, expected",
    [("market", "MARKET"), ("limit", "LIMIT"), ("stop_limit", "STOP_LIMIT")],
)
def test_validate_order_type_normalizes_case(order_type: str, expected: str) -> None:
    assert validate_order_type(order_type) == expected


@pytest.mark.parametrize("order_type", ["iceberg", "", None])
def test_validate_order_type_rejects_invalid_values(order_type: object) -> None:
    with pytest.raises(ValidationError):
        validate_order_type(order_type)


@pytest.mark.parametrize("quantity", [0.001, "1", "2.5"])
def test_validate_quantity_accepts_positive_values(quantity: object) -> None:
    assert validate_quantity(quantity) > 0


@pytest.mark.parametrize("quantity", [0, -1, "abc", None])
def test_validate_quantity_rejects_invalid_values(quantity: object) -> None:
    with pytest.raises(ValidationError):
        validate_quantity(quantity)


@pytest.mark.parametrize("price", [1, 27350.5, "0.01"])
def test_validate_price_accepts_positive_values(price: object) -> None:
    assert validate_price(price) > 0


@pytest.mark.parametrize("price", [0, -0.1, "abc", None])
def test_validate_price_rejects_invalid_values(price: object) -> None:
    with pytest.raises(ValidationError):
        validate_price(price)


@pytest.mark.parametrize("stop_price", [1, 27300.5, "0.01"])
def test_validate_stop_price_accepts_positive_values(stop_price: object) -> None:
    assert validate_stop_price(stop_price) > 0


@pytest.mark.parametrize("stop_price", [0, -0.1, "abc", None])
def test_validate_stop_price_rejects_invalid_values(stop_price: object) -> None:
    with pytest.raises(ValidationError):
        validate_stop_price(stop_price)
