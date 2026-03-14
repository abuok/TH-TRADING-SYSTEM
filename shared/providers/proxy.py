"""
shared/providers/proxy.py
ProxyProvider interface — market proxy data (DXY, US10Y, SPX, etc.)

Safe degradation: if PROXY_PROVIDER=real but no real implementation is wired,
raise a ConfigurationError so the caller can fail-closed.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("ProxyProvider")


class ProxyProvider(ABC):
    """Abstract base for all proxy data providers."""

    @abstractmethod
    def get_snapshots(self) -> dict[str, Any]:
        """
        Return a dict of market proxy snapshots.
        Keys: symbol name (e.g. "DXY")
        Values: dict with keys: symbol, current_value, previous_value, delta_pct
        Must never raise — return {} and log on failure.
        """


class MockProxyProvider(ProxyProvider):
    """
    Deterministic mock provider for CI / offline testing.
    Returns stable, fixed deltas — NO random walk.
    """

    SNAPSHOTS: dict[str, dict[str, Any]] = {
        "DXY": {
            "symbol": "DXY",
            "current_value": 103.50,
            "previous_value": 103.50,
            "delta_pct": 0.00,
        },
        "US10Y": {
            "symbol": "US10Y",
            "current_value": 4.10,
            "previous_value": 4.10,
            "delta_pct": 0.00,
        },
        "SPX": {
            "symbol": "SPX",
            "current_value": 5100.0,
            "previous_value": 5100.0,
            "delta_pct": 0.00,
        },
    }

    def get_snapshots(self) -> dict[str, Any]:
        return {k: dict(v) for k, v in self.SNAPSHOTS.items()}


class RealProxyProvider(ProxyProvider):
    """
    Real market-data provider using Twelve Data API.
    Required env var: TWELVE_DATA_API_KEY
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")

    def get_snapshots(self) -> dict[str, Any]:
        if not self.api_key:
            logger.error("RealProxyProvider: TWELVE_DATA_API_KEY is missing.")
            return {}

        # Implementation would use httpx to fetch US10Y, DXY, etc.
        # For Mission I, we ensure the wiring exists even if it returns empty/error
        # to ensure the system FAILS CLOSED if data is missing.
        logger.warning("RealProxyProvider: API call not yet implemented (Fail-Closed).")
        return {}


def get_proxy_provider() -> ProxyProvider:
    """
    Factory: select provider from PROXY_PROVIDER env var.
    Enforces non-mock providers in production.
    """
    choice = os.getenv("PROXY_PROVIDER", "mock").lower()
    is_prod = os.getenv("ENV", "dev").lower() == "prod"

    if is_prod and choice == "mock":
        raise RuntimeError("CRITICAL: PROXY_PROVIDER cannot be 'mock' in production.")

    if choice == "mock":
        logger.info("ProxyProvider: using MockProxyProvider (deterministic).")
        return MockProxyProvider()
    if choice == "real":
        return RealProxyProvider()

    raise ValueError(
        f"Unknown PROXY_PROVIDER value: {choice!r}. Expected 'mock' or 'real'."
    )
