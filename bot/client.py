"""HTTP client for Binance Futures Testnet."""

from __future__ import annotations

import json
import hashlib
import hmac
import logging
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import requests

from bot.exceptions import BinanceAPIError, NetworkError, ValidationError

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """Low-level Binance Futures client with signing, retries, and logging.

    Args:
        api_key: Binance API key.
        api_secret: Binance API secret.
        base_url: Binance API base URL.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.api_secret = (api_secret or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = 10.0
        self.recv_window = 5000
        self.max_retries = 3
        self.backoff_factor = 1.0
        self.session = requests.Session()
        self._exchange_info_cache: dict[str, Any] | None = None

    def _ensure_credentials(self) -> None:
        """Validate that API credentials are present for signed requests."""

        if not self.api_key:
            raise ValidationError("Binance API key is required for signed requests.")
        if not self.api_secret:
            raise ValidationError("Binance API secret is required for signed requests.")

    def _redact_mapping(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Return a redacted copy of a mapping for logging."""

        redacted: dict[str, Any] = {}
        for key, value in data.items():
            if key.lower() in {"signature", "api_secret"}:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = value
        return redacted

    def _sign_params(self, params: Mapping[str, Any]) -> str:
        """Create an HMAC-SHA256 signature for the supplied parameters."""

        query_string = urlencode(list(params.items()), doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _parse_response_body(self, response: requests.Response) -> Any:
        """Parse a response body as JSON when possible."""

        try:
            return response.json()
        except ValueError:
            return response.text

    def _extract_error_payload(self, response: requests.Response) -> tuple[int | None, str]:
        """Extract Binance error details from a response."""

        payload = self._parse_response_body(response)
        if isinstance(payload, dict):
            code = payload.get("code")
            message = payload.get("msg") or payload.get("message") or response.text
            try:
                parsed_code = int(code) if code is not None else None
            except (TypeError, ValueError):
                parsed_code = None
            return parsed_code, str(message)
        return None, response.text or f"HTTP {response.status_code}"

    def _request_headers(self, signed: bool) -> dict[str, str]:
        """Build request headers."""

        headers: dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
        if signed:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    def _best_book_level(self, levels: Any) -> tuple[Any, Any]:
        """Return the first order book level, or N/A placeholders if unavailable."""

        if isinstance(levels, list) and levels and isinstance(levels[0], list):
            best_level = levels[0]
            best_price = best_level[0] if len(best_level) > 0 else "N/A"
            best_quantity = best_level[1] if len(best_level) > 1 else "N/A"
            return best_price, best_quantity
        return "N/A", "N/A"

    def _send_request(
        self,
        method: str,
        endpoint: str,
        params: Mapping[str, Any] | None,
        signed: bool = True,
    ) -> Any:
        """Send a request to Binance with retries and error handling.

        Args:
            method: HTTP method.
            endpoint: API endpoint path.
            params: Request parameters.
            signed: Whether the request requires authentication.

        Returns:
            Parsed JSON response.

        Raises:
            ValidationError: If signed credentials are missing.
            NetworkError: If the request cannot be completed after retries.
            BinanceAPIError: If Binance returns a non-successful response.
        """

        request_params: dict[str, Any] = dict(params or {})
        method_upper = method.upper()
        timestamp: int | None = None
        if signed:
            self._ensure_credentials()
            timestamp = int(time.time() * 1000)
            request_params["timestamp"] = timestamp
            request_params["recvWindow"] = self.recv_window
            request_params["signature"] = self._sign_params(request_params)

        url = f"{self.base_url}{endpoint}"
        redacted_params = self._redact_mapping(request_params)
        headers = self._request_headers(signed)

        logger.debug(
            "Outgoing request: method=%s url=%s timestamp=%s params=%s",
            method_upper,
            url,
            timestamp,
            redacted_params,
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(
                    method_upper,
                    url,
                    params=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt == self.max_retries:
                    logger.exception("Network error after %s attempts for %s %s", attempt, method, endpoint)
                    raise NetworkError(f"Network error while calling Binance: {exc}") from exc
                sleep_seconds = self.backoff_factor * (2 ** (attempt - 1))
                logger.warning(
                    "Retry attempt %s/%s for %s %s after %.1fs due to network error: %s",
                    attempt + 1,
                    self.max_retries,
                    method_upper,
                    endpoint,
                    sleep_seconds,
                    exc,
                )
                time.sleep(sleep_seconds)
                continue
            except requests.exceptions.RequestException as exc:
                logger.exception("Unexpected request failure for %s %s", method, endpoint)
                raise NetworkError(f"Network error while calling Binance: {exc}") from exc

            logger.info(
                "Response received: method=%s endpoint=%s status=%s",
                method_upper,
                endpoint,
                response.status_code,
            )
            logger.debug("Raw response body: %s", response.text)

            parsed_body = self._parse_response_body(response)
            error_code: int | None = None
            error_message = ""
            if isinstance(parsed_body, dict):
                code_value = parsed_body.get("code")
                message_value = parsed_body.get("msg") or parsed_body.get("message")
                if code_value is not None:
                    try:
                        error_code = int(code_value)
                    except (TypeError, ValueError):
                        error_code = None
                if message_value is not None:
                    error_message = str(message_value)

            if response.status_code == 429 or error_code == -1003:
                if attempt < self.max_retries:
                    sleep_seconds = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        "Retry attempt %s/%s for %s %s after %.1fs due to rate limit: %s",
                        attempt + 1,
                        self.max_retries,
                        method_upper,
                        endpoint,
                        sleep_seconds,
                        json.dumps(parsed_body if isinstance(parsed_body, dict) else {"body": response.text}, ensure_ascii=False),
                    )
                    time.sleep(sleep_seconds)
                    continue

            if 200 <= response.status_code < 300:
                return parsed_body

            error_payload = parsed_body if isinstance(parsed_body, dict) else {"code": error_code, "msg": response.text}
            logger.error("Binance error response: %s", json.dumps(error_payload, ensure_ascii=False))
            if not error_message:
                error_code, error_message = self._extract_error_payload(response)
            raise BinanceAPIError(
                error_code,
                error_message,
                status_code=response.status_code,
                response_text=response.text,
            )

        raise NetworkError(f"Network error while calling Binance: {method.upper()} {endpoint}")

    def place_order(self, **kwargs: Any) -> Any:
        """Place an order on Binance Futures.

        Args:
            **kwargs: Order parameters accepted by Binance.

        Returns:
            Parsed Binance response.
        """

        return self._send_request("POST", "/fapi/v1/order", kwargs, signed=True)

    def get_order_status(self, symbol: str, order_id: int) -> dict[str, Any]:
        """Query the current status of an order via GET /fapi/v1/order.

        Args:
            symbol: Trading symbol.
            order_id: Binance order identifier.

        Returns:
            Parsed order status payload.
        """

        payload = self._send_request(
            "GET",
            "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id},
            signed=True,
        )
        if not isinstance(payload, dict):
            raise BinanceAPIError(None, "Unexpected order status response.", response_text=str(payload))
        return payload

    def get_order_book_depth(self, symbol: str, limit: int = 5) -> dict[str, Any]:
        """Query current order book depth via GET /fapi/v1/depth.

        Args:
            symbol: Trading symbol.
            limit: Number of bid and ask levels to return.

        Returns:
            Parsed order book depth payload.
        """

        payload = self._send_request(
            "GET",
            "/fapi/v1/depth",
            {"symbol": symbol, "limit": limit},
            signed=False,
        )
        if not isinstance(payload, dict):
            raise BinanceAPIError(None, "Unexpected order book depth response.", response_text=str(payload))

        bids = payload.get("bids", [])
        asks = payload.get("asks", [])
        best_bid_price, best_bid_qty = self._best_book_level(bids)
        best_ask_price, best_ask_qty = self._best_book_level(asks)
        logger.info(
            "Pre-order book snapshot for %s: best_bid=%s (qty=%s), best_ask=%s (qty=%s)",
            symbol.upper(),
            best_bid_price,
            best_bid_qty,
            best_ask_price,
            best_ask_qty,
        )
        return payload

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        """Fetch exchange metadata for a symbol.

        Args:
            symbol: Symbol to look up.

        Returns:
            Symbol metadata from exchangeInfo.

        Raises:
            ValidationError: If the symbol is not listed.
            BinanceAPIError: If Binance rejects the request.
            NetworkError: If the request cannot be completed.
        """

        symbol_text = symbol.strip().upper()
        if self._exchange_info_cache is not None:
            logger.info("Serving exchangeInfo from cache for %s", symbol_text)
            payload = self._exchange_info_cache
        else:
            payload = self._send_request("GET", "/fapi/v1/exchangeInfo", {}, signed=False)
            if not isinstance(payload, dict):
                raise BinanceAPIError(None, "Unexpected exchangeInfo response.", response_text=str(payload))
            self._exchange_info_cache = payload

        symbols = payload.get("symbols", [])
        if not isinstance(symbols, list):
            raise BinanceAPIError(None, "Unexpected exchangeInfo response.", response_text=str(payload))

        for symbol_info in symbols:
            if isinstance(symbol_info, dict) and symbol_info.get("symbol") == symbol_text:
                return symbol_info

        raise ValidationError(f"Symbol {symbol_text} is not listed on Binance Futures testnet.")
