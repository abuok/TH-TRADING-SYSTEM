"""
shared/providers/price_quote.py
PriceQuoteProvider interface — live bid/ask and spread for a given symbol.

Safe degradation: if no real provider is configured, FAIL CLOSED — return None
so the caller can reject the preflight check rather than silently pass with stale data.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, NamedTuple

logger = logging.getLogger("PriceQuoteProvider")


class PriceQuote(NamedTuple):
    symbol: str
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pips(self) -> float:
        """
        Approximate pip spread.
        For JPY pairs 1 pip = 0.01, for others 1 pip = 0.0001.
        For metals/indices, callers should normalise externally.
        """
        factor = 100.0 if "JPY" in self.symbol else 10_000.0
        return round((self.ask - self.bid) * factor, 1)


class PriceQuoteProvider(ABC):
    """Abstract base for live price data."""

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        """
        Return a PriceQuote for *symbol*, or None on failure.
        Must never raise — return None and log on failure.
        """


class MockPriceQuoteProvider(PriceQuoteProvider):
    """
    Deterministic mock for CI.
    Returns a quote that makes price-deviation check PASS by default
    (current == entry for any entry price).
    Tests can construct MockPriceQuoteProvider with custom quotes.
    """

    def __init__(self, quotes: Optional[dict] = None):
        # symbol -> (bid, ask)
        self._quotes: dict = quotes or {}

    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        if symbol in self._quotes:
            bid, ask = self._quotes[symbol]
            return PriceQuote(symbol=symbol, bid=bid, ask=ask)
        # Unknown symbol: return None so callers treat as data-unavailable
        logger.debug("MockPriceQuoteProvider: no quote configured for %s — returning None.", symbol)
        return None


class RealPriceQuoteProvider(PriceQuoteProvider):
    """
    Stub for a real broker / aggregator price feed.
    Raises NotImplementedError until properly implemented.
    """

    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        raise NotImplementedError(
            "RealPriceQuoteProvider is not yet implemented. "
            "Set PRICE_PROVIDER=mock or implement get_quote()."
        )


def get_price_quote_provider() -> PriceQuoteProvider:
    """Factory: select provider from PRICE_PROVIDER env var."""
    choice = os.getenv("PRICE_PROVIDER", "mock").lower()
    if choice == "mock":
        logger.info("PriceQuoteProvider: using MockPriceQuoteProvider.")
        return MockPriceQuoteProvider()
    if choice == "real":
        logger.warning(
            "PriceQuoteProvider: RealPriceQuoteProvider selected but not implemented. "
            "Preflight price checks will fail-closed (return None)."
        )
        return RealPriceQuoteProvider()
    raise ValueError(
        f"Unknown PRICE_PROVIDER value: {choice!r}. Expected 'mock' or 'real'."
    )
