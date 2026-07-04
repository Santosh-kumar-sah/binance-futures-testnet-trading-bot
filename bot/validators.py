"""Pure validation helpers for trading bot inputs."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from bot.exceptions import ValidationError

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+USDT$")
_ALLOWED_SIDES = {"BUY", "SELL"}
_ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LIMIT"}


def _to_positive_decimal(value: object, field_name: str) -> Decimal:
    """Convert a value to a positive Decimal.

    Args:
        value: User-provided value.
        field_name: Name of the validated field for error messages.

    Returns:
        A positive Decimal value.

    Raises:
        ValidationError: If the value is missing, not numeric, or not positive.
    """

    if value is None:
        raise ValidationError(f"{field_name} is required.")
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValidationError(f"{field_name} must be a valid number.") from None
    if decimal_value <= 0:
        raise ValidationError(f"{field_name} must be greater than 0.")
    return decimal_value


def validate_symbol(symbol: object) -> str:
    """Validate and normalize a futures symbol.

    Args:
        symbol: Symbol provided by the user.

    Returns:
        The validated uppercase symbol.

    Raises:
        ValidationError: If the symbol is missing or malformed.
    """

    if symbol is None:
        raise ValidationError("symbol is required.")
    symbol_text = str(symbol).strip().upper()
    if not symbol_text:
        raise ValidationError("symbol cannot be empty.")
    if not _SYMBOL_PATTERN.fullmatch(symbol_text):
        raise ValidationError(
            "symbol must be uppercase, alphanumeric, and end with USDT."
        )
    return symbol_text


def validate_side(side: object) -> str:
    """Validate and normalize order side.

    Args:
        side: Side provided by the user.

    Returns:
        The validated uppercase side.

    Raises:
        ValidationError: If the side is missing or invalid.
    """

    if side is None:
        raise ValidationError("side is required.")
    side_text = str(side).strip().upper()
    if side_text not in _ALLOWED_SIDES:
        raise ValidationError("side must be BUY or SELL.")
    return side_text


def validate_order_type(order_type: object) -> str:
    """Validate and normalize the order type.

    Args:
        order_type: Order type provided by the user.

    Returns:
        The validated uppercase order type.

    Raises:
        ValidationError: If the order type is missing or invalid.
    """

    if order_type is None:
        raise ValidationError("type is required.")
    order_type_text = str(order_type).strip().upper()
    if order_type_text not in _ALLOWED_ORDER_TYPES:
        raise ValidationError("type must be MARKET, LIMIT, or STOP_LIMIT.")
    return order_type_text


def validate_quantity(quantity: object) -> float:
    """Validate that quantity is a positive numeric value.

    Args:
        quantity: Quantity provided by the user.

    Returns:
        Quantity as a float.

    Raises:
        ValidationError: If the quantity is missing or invalid.
    """

    decimal_value = _to_positive_decimal(quantity, "quantity")
    return float(decimal_value)


def validate_price(price: object) -> float:
    """Validate that price is a positive numeric value.

    Args:
        price: Price provided by the user.

    Returns:
        Price as a float.

    Raises:
        ValidationError: If the price is missing or invalid.
    """

    decimal_value = _to_positive_decimal(price, "price")
    return float(decimal_value)


def validate_stop_price(stop_price: object) -> float:
    """Validate that stop price is a positive numeric value.

    Args:
        stop_price: Stop price provided by the user.

    Returns:
        Stop price as a float.

    Raises:
        ValidationError: If the stop price is missing or invalid.
    """

    decimal_value = _to_positive_decimal(stop_price, "stop_price")
    return float(decimal_value)
