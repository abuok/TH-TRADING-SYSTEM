"""
shared/providers/symbol_spec.py
Provides contract details (min_lot, tick_size, etc.) for a symbol.
Used for lot sizing and risk calculations.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, NamedTuple
from sqlalchemy.orm import Session
import shared.database.session as db_session
from shared.database.models import SymbolSpec as SymbolSpecModel

logger = logging.getLogger("SymbolSpecProvider")

class SymbolSpec(NamedTuple):
    symbol: str
    contract_size: float
    tick_size: float
    tick_value: float
    pip_size: float
    min_lot: float
    lot_step: float

class SymbolSpecProvider(ABC):
    @abstractmethod
    def get_spec(self, symbol: str) -> Optional[SymbolSpec]:
        """Return SymbolSpec for symbol, or None if not found."""

class DBSymbolSpecProvider(SymbolSpecProvider):
    """
    Fetches symbol specs from the database.
    Specs are populated via the /bridge/spec endpoint from MT5.
    """
    def __init__(self, db: Optional[Session] = None):
        self._db = db

    def get_spec(self, symbol: str) -> Optional[SymbolSpec]:
        db = self._db or db_session.SessionLocal()
        try:
            model = db.query(SymbolSpecModel).filter(SymbolSpecModel.symbol == symbol).first()
            if not model:
                return None
            return SymbolSpec(
                symbol=model.symbol,
                contract_size=model.contract_size,
                tick_size=model.tick_size,
                tick_value=model.tick_value,
                pip_size=model.pip_size,
                min_lot=model.min_lot,
                lot_step=model.lot_step
            )
        finally:
            if not self._db:
                db.close()

class MockSymbolSpecProvider(SymbolSpecProvider):
    """Deterministic mock for tests/research."""
    def __init__(self):
        self._specs = {
            "XAUUSD": SymbolSpec("XAUUSD", 100.0, 0.01, 1.0, 0.01, 0.01, 0.01),
            "GBPJPY": SymbolSpec("GBPJPY", 100000.0, 0.001, 0.01, 0.01, 0.01, 0.01),
            "EURUSD": SymbolSpec("EURUSD", 100000.0, 0.00001, 1.0, 0.0001, 0.01, 0.01)
        }

    def get_spec(self, symbol: str) -> Optional[SymbolSpec]:
        return self._specs.get(symbol)

def get_symbol_spec_provider() -> SymbolSpecProvider:
    """Factory: select spec provider. Enforces non-mock in production."""
    choice = os.getenv("SPEC_PROVIDER", "mock").lower()
    is_prod = os.getenv("ENV", "dev").lower() == "prod"

    if is_prod and choice == "mock":
        raise RuntimeError("CRITICAL: SPEC_PROVIDER cannot be 'mock' in production.")

    if choice == "mock":
        return MockSymbolSpecProvider()
    return DBSymbolSpecProvider()
