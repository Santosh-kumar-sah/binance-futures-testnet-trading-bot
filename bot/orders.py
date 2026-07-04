"""Order service for Binance Futures testnet."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from bot.client import BinanceFuturesClient
from bot.exceptions import ValidationError
from bot.validators import (
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_stop_price,
    validate_symbol,
)

logger = logging.getLogger(__name__)


class OrderService:
    """Build, validate, and submit Binance Futures orders.

    Args:
        client: A configured BinanceFuturesClient instance.
    """

    def __init__(self, client: BinanceFuturesClient) -> None:
        self.client = client

    def _format_decimal(self, value: float | Decimal) -> str:
        """Format a numeric value for Binance API submission."""

        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        normalized = decimal_value.normalize()
        if normalized == normalized.to_integral():
            return format(normalized.quantize(Decimal("1")), "f")
        return format(normalized, "f")

    def _extract_filter(self, symbol_info: Mapping[str, Any], filter_type: str) -> dict[str, Any]:
        """Return a specific exchange filter from symbol metadata."""

        filters = symbol_info.get("filters", [])
        if not isinstance(filters, list):
            raise ValidationError(f"Symbol {symbol_info.get('symbol', 'UNKNOWN')} has invalid filter metadata.")
        for exchange_filter in filters:
            if isinstance(exchange_filter, dict) and exchange_filter.get("filterType") == filter_type:
                return exchange_filter
        raise ValidationError(
            f"Symbol {symbol_info.get('symbol', 'UNKNOWN')} does not expose {filter_type} metadata."
        )

    def _extract_symbol_rules(self, symbol: str, symbol_info: Mapping[str, Any]) -> dict[str, Decimal]:
        """Extract symbol precision rules from exchange metadata."""

        lot_size = self._extract_filter(symbol_info, "LOT_SIZE")
        price_filter = self._extract_filter(symbol_info, "PRICE_FILTER")
        try:
            min_qty = Decimal(str(lot_size["minQty"]))
            step_size = Decimal(str(lot_size["stepSize"]))
            min_price = Decimal(str(price_filter["minPrice"]))
            tick_size = Decimal(str(price_filter["tickSize"]))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError(f"Symbol {symbol} has invalid filter metadata.") from exc

        logger.info(
            "Fetched symbol filters for %s: stepSize=%s, tickSize=%s, minQty=%s",
            symbol,
            self._format_decimal(step_size),
            self._format_decimal(tick_size),
            self._format_decimal(min_qty),
        )
        return {
            "minQty": min_qty,
            "stepSize": step_size,
            "minPrice": min_price,
            "tickSize": tick_size,
        }

    def _validate_quantized_value(
        self,
        *,
        value_name: str,
        value: Decimal,
        symbol: str,
        minimum: Decimal,
        step: Decimal,
    ) -> None:
        """Validate that a value satisfies a Binance filter step size."""

        if value < minimum:
            raise ValidationError(
                f"{value_name.title()} {self._format_decimal(value)} is invalid for {symbol} — must be a multiple of stepSize {self._format_decimal(step)} (min: {self._format_decimal(minimum)})"
            )
        if ((value - minimum) % step) != 0:
            raise ValidationError(
                f"{value_name.title()} {self._format_decimal(value)} is invalid for {symbol} — must be a multiple of stepSize {self._format_decimal(step)} (min: {self._format_decimal(minimum)})"
            )

    def _validate_price_constraints(
        self,
        symbol: str,
        price: Decimal,
        rules: Mapping[str, Decimal],
        field_name: str,
    ) -> None:
        """Validate price or stop price against Binance PRICE_FILTER rules."""

        min_price = rules["minPrice"]
        tick_size = rules["tickSize"]
        if price < min_price or ((price - min_price) % tick_size) != 0:
            raise ValidationError(
                f"{field_name.replace('_', ' ').title()} {self._format_decimal(price)} is invalid for {symbol} — must be a multiple of tickSize {self._format_decimal(tick_size)} (min: {self._format_decimal(min_price)})"
            )

    def _parse_quantity(self, quantity: float) -> Decimal:
        """Convert a quantity to Decimal for precise filter validation."""

        return Decimal(str(quantity))

    def _parse_price(self, price: float) -> Decimal:
        """Convert a price to Decimal for precise filter validation."""

        return Decimal(str(price))

    def _normalize_order_response(self, response: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize a Binance order payload into the bot response schema."""

        normalized = {
            "orderId": response.get("orderId"),
            "symbol": response.get("symbol"),
            "status": response.get("status"),
            "clientOrderId": response.get("clientOrderId"),
            "price": response.get("price"),
            "avgPrice": response.get("avgPrice") or "N/A",
            "origQty": response.get("origQty"),
            "executedQty": response.get("executedQty"),
            "cumQuote": response.get("cumQuote"),
            "timeInForce": response.get("timeInForce"),
            "type": response.get("type"),
            "reduceOnly": response.get("reduceOnly"),
            "closePosition": response.get("closePosition"),
            "side": response.get("side"),
            "positionSide": response.get("positionSide"),
            "stopPrice": response.get("stopPrice"),
            "workingType": response.get("workingType"),
            "priceProtect": response.get("priceProtect"),
            "origType": response.get("origType"),
            "updateTime": response.get("updateTime"),
            "updateTimeUtc": self._format_update_time(response.get("updateTime")),
        }
        return normalized

    def _log_order_response_payload(self, normalized: Mapping[str, Any]) -> None:
        """Log the full normalized order payload."""

        logger.info("Order response payload: %s", json.dumps(normalized, ensure_ascii=False, default=str))

    def _submit_and_normalize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Submit an order and normalize the response payload."""

        response = self.client.place_order(**params)
        if not isinstance(response, dict):
            raise ValidationError("Unexpected order response from Binance.")

        return self._normalize_order_response(response)

    def _poll_order_status_until_filled(
        self,
        symbol: str,
        order_id: Any,
        initial_response: dict[str, Any],
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Poll Binance until a market order is FILLED or retries are exhausted."""

        final_response = dict(initial_response)
        for attempt in range(1, max_retries + 1):
            logger.info(
                "Polling order status for %s orderId=%s (attempt %s/%s)",
                symbol,
                order_id,
                attempt,
                max_retries,
            )
            time.sleep(0.5)
            status_response = self.client.get_order_status(symbol, int(order_id))
            logger.info(
                "Polled order status for %s orderId=%s: status=%s executedQty=%s",
                symbol,
                order_id,
                status_response.get("status", "N/A"),
                status_response.get("executedQty", "N/A"),
            )
            final_response = dict(status_response)
            if status_response.get("status") == "FILLED":
                break
        if final_response.get("status") != "FILLED":
            logger.warning(
                "Order accepted but not yet filled after polling. Last known status: %s | final_response=%s",
                final_response.get("status", "N/A"),
                json.dumps(final_response, ensure_ascii=False, default=str),
            )
        return final_response

    def _apply_market_preflight(self, symbol: str) -> None:
        """Capture a depth snapshot before a market order is sent."""

        self.client.get_order_book_depth(symbol)

    def _format_update_time(self, update_time: Any) -> str:
        """Convert a millisecond update time to UTC text."""

        if update_time in (None, "", 0):
            return "N/A"
        try:
            timestamp_seconds = int(update_time) / 1000.0
            return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (TypeError, ValueError, OSError):
            return "N/A"

    def _log_request_summary(self, params: Mapping[str, Any]) -> None:
        """Log a compact summary before sending an order."""

        logger.info(
            "Order request summary: symbol=%s side=%s type=%s quantity=%s price=%s stopPrice=%s timeInForce=%s",
            params.get("symbol"),
            params.get("side"),
            params.get("type"),
            params.get("quantity", "N/A"),
            params.get("price", "N/A"),
            params.get("stopPrice", "N/A"),
            params.get("timeInForce", "N/A"),
        )

    def place_market_order(self, symbol: str, side: str, quantity: float) -> dict[str, Any]:
        """Place a market order.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            quantity: Order quantity.

        Returns:
            Normalized order response payload.
        """

        symbol_text = validate_symbol(symbol)
        side_text = validate_side(side)
        validate_order_type("MARKET")
        quantity_value = validate_quantity(quantity)
        symbol_info = self.client.get_symbol_info(symbol_text)
        rules = self._extract_symbol_rules(symbol_text, symbol_info)
        quantity_decimal = self._parse_quantity(quantity_value)
        self._validate_quantized_value(
            value_name="Quantity",
            value=quantity_decimal,
            symbol=symbol_text,
            minimum=rules["minQty"],
            step=rules["stepSize"],
        )

        self._apply_market_preflight(symbol_text)
        params = {
            "symbol": symbol_text,
            "side": side_text,
            "type": "MARKET",
            "quantity": self._format_decimal(quantity_value),
        }
        self._log_request_summary(params)
        initial_response = self._submit_and_normalize(params)
        order_id = initial_response.get("orderId")
        if order_id is None:
            self._log_order_response_payload(initial_response)
            return initial_response
        final_response = self._poll_order_status_until_filled(symbol_text, order_id, initial_response)
        self._log_order_response_payload(final_response)
        return final_response

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Place a limit order.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            quantity: Order quantity.
            price: Limit price.
            time_in_force: Time in force policy.

        Returns:
            Normalized order response payload.
        """

        symbol_text = validate_symbol(symbol)
        side_text = validate_side(side)
        validate_order_type("LIMIT")
        quantity_value = validate_quantity(quantity)
        price_value = validate_price(price)
        symbol_info = self.client.get_symbol_info(symbol_text)
        rules = self._extract_symbol_rules(symbol_text, symbol_info)
        quantity_decimal = self._parse_quantity(quantity_value)
        price_decimal = self._parse_price(price_value)
        self._validate_quantized_value(
            value_name="Quantity",
            value=quantity_decimal,
            symbol=symbol_text,
            minimum=rules["minQty"],
            step=rules["stepSize"],
        )
        self._validate_price_constraints(symbol_text, price_decimal, rules, "Price")

        params = {
            "symbol": symbol_text,
            "side": side_text,
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "quantity": self._format_decimal(quantity_value),
            "price": self._format_decimal(price_value),
        }
        self._log_request_summary(params)
        response = self._submit_and_normalize(params)
        self._log_order_response_payload(response)
        return response

    def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Place a stop-limit order.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            quantity: Order quantity.
            price: Limit price.
            stop_price: Trigger price.
            time_in_force: Time in force policy.

        Returns:
            Normalized order response payload.
        """

        symbol_text = validate_symbol(symbol)
        side_text = validate_side(side)
        validate_order_type("STOP_LIMIT")
        quantity_value = validate_quantity(quantity)
        price_value = validate_price(price)
        stop_price_value = validate_stop_price(stop_price)
        symbol_info = self.client.get_symbol_info(symbol_text)
        rules = self._extract_symbol_rules(symbol_text, symbol_info)
        quantity_decimal = self._parse_quantity(quantity_value)
        price_decimal = self._parse_price(price_value)
        stop_price_decimal = self._parse_price(stop_price_value)
        self._validate_quantized_value(
            value_name="Quantity",
            value=quantity_decimal,
            symbol=symbol_text,
            minimum=rules["minQty"],
            step=rules["stepSize"],
        )
        self._validate_price_constraints(symbol_text, price_decimal, rules, "Price")
        self._validate_price_constraints(symbol_text, stop_price_decimal, rules, "Stop price")

        params = {
            "symbol": symbol_text,
            "side": side_text,
            "type": "STOP",
            "timeInForce": time_in_force,
            "quantity": self._format_decimal(quantity_value),
            "price": self._format_decimal(price_value),
            "stopPrice": self._format_decimal(stop_price_value),
        }
        self._log_request_summary(params)
        response = self._submit_and_normalize(params)
        self._log_order_response_payload(response)
        return response
