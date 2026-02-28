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
from sqlalchemy.orm import Session

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


class DBPriceQuoteProvider(PriceQuoteProvider):
    """
    Fetches real-time price quotes from the database.
    Quotes are updated via the /bridge/quote endpoint.
    """
    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        from shared.database.models import LiveQuote
        import shared.database.session as db_session
        
        db = self._db or db_session.SessionLocal()
        try:
            model = db.query(LiveQuote).filter(LiveQuote.symbol == symbol).first()
            if not model:
                return None
            return PriceQuote(symbol=model.symbol, bid=model.bid, ask=model.ask)
        finally:
            if not self._db:
                db.close()

class RealPriceQuoteProvider(PriceQuoteProvider):
    """Stub for future direct broker integration."""
    def get_quote(self, symbol: str) -> Optional[PriceQuote]:
        return None

def get_price_quote_provider() -> PriceQuoteProvider:
    """Factory: select provider from PRICE_PROVIDER env var."""
    choice = os.getenv("PRICE_PROVIDER", "mock").lower()
    if choice == "mock":
        return MockPriceQuoteProvider()
    if choice == "db":
        return DBPriceQuoteProvider()
    if choice == "real":
        return RealPriceQuoteProvider()
    return MockPriceQuoteProvider()
