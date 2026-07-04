"""Custom exceptions for the trading bot."""

from __future__ import annotations


class TradingBotError(Exception):
    """Base class for trading bot errors."""


class ValidationError(TradingBotError):
    """Raised when user input or symbol constraints are invalid."""


class NetworkError(TradingBotError):
    """Raised when a network or transport failure prevents a request."""


class BinanceAPIError(TradingBotError):
    """Raised when Binance returns a non-successful API response.

    Attributes:
        code: Binance error code, when available.
        message: Human-readable error message.
        status_code: HTTP status code returned by Binance, when available.
        response_text: Raw response body returned by Binance.
    """

    def __init__(
        self,
        code: int | None,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(self.__str__())

    def __str__(self) -> str:
        """Return a compact error description."""
        if self.code is None:
            return self.message
        return f"Binance API error {self.code}: {self.message}"
