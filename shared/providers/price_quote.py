"""
shared/providers/price_quote.py
PriceQuoteProvider interface — live bid/ask and spread for a given symbol.

Safe degradation: if no real provider is configured, FAIL CLOSED — return None
so the caller can reject the preflight check rather than silently pass with stale data.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import NamedTuple

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
    def get_quote(self, symbol: str) -> PriceQuote | None:
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

    def __init__(self, quotes: dict | None = None):
        # symbol -> (bid, ask)
        self._quotes: dict = quotes or {}

    def get_quote(self, symbol: str) -> PriceQuote | None:
        if symbol in self._quotes:
            bid, ask = self._quotes[symbol]
            return PriceQuote(symbol=symbol, bid=bid, ask=ask)
        logger.debug(
            "MockPriceQuoteProvider: no quote configured for %s — returning None.",
            symbol,
        )
        return None

    def set_quote(self, symbol: str, bid: float, ask: float):
        self._quotes[symbol] = (bid, ask)


class DBPriceQuoteProvider(PriceQuoteProvider):
    """
    Fetches real-time price quotes from the database.
    Quotes are updated via the /bridge/quote endpoint.
    """

    def __init__(self, db: Session | None = None):
        self._db = db

    def get_quote(self, symbol: str) -> PriceQuote | None:
        import shared.database.session as db_session
        from shared.database.models import LiveQuote

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
    """
    Production integration: fetches live quotes directly from Redis in O(1) time.
    Bypasses the database entirely to prevent Postgres lock contention under high load.
    The Bridge (services/bridge/main.py) pushes to quote:{symbol} on every tick.
    """
    def __init__(self):
        from shared.messaging.event_bus import EventBus
        self.bus = EventBus()

    def get_quote(self, symbol: str) -> PriceQuote | None:
        import json
        raw = self.bus.client.get(f"quote:{symbol}")
        if not raw:
            return None
            
        try:
            data = json.loads(raw)
            return PriceQuote(
                symbol=data["symbol"], 
                bid=float(data["bid"]), 
                ask=float(data["ask"])
            )
        except Exception as e:
            logger.error(f"Failed to parse quote from Redis for {symbol}: {e}")
            return None


_global_provider: PriceQuoteProvider | None = None


def get_price_quote_provider() -> PriceQuoteProvider:
    """Factory: select provider from PRICE_PROVIDER env var, or return global override."""
    global _global_provider
    if _global_provider:
        return _global_provider

    choice = os.getenv("PRICE_PROVIDER", "mock").lower()
    is_prod = os.getenv("ENV", "dev").lower() == "prod"

    if is_prod and choice == "mock":
        raise RuntimeError("CRITICAL: PRICE_PROVIDER cannot be 'mock' in production.")

    if choice == "mock":
        return MockPriceQuoteProvider()
    if choice == "db":
        return DBPriceQuoteProvider()
    if choice == "real":
        return RealPriceQuoteProvider()
    return MockPriceQuoteProvider()


def set_price_quote_provider(provider: PriceQuoteProvider):
    """Override the global price quote provider (useful for testing)."""
    global _global_provider
    _global_provider = provider
