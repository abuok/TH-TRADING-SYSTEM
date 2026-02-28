"""
shared/providers/proxy.py
ProxyProvider interface — market proxy data (DXY, US10Y, SPX, etc.)

Safe degradation: if PROXY_PROVIDER=real but no real implementation is wired,
raise a ConfigurationError so the caller can fail-closed.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger("ProxyProvider")


class ProxyProvider(ABC):
    """Abstract base for all proxy data providers."""

    @abstractmethod
    def get_snapshots(self) -> Dict[str, Any]:
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

    SNAPSHOTS: Dict[str, Dict[str, Any]] = {
        "DXY":   {"symbol": "DXY",   "current_value": 103.50, "previous_value": 103.50, "delta_pct": 0.00},
        "US10Y": {"symbol": "US10Y", "current_value":   4.10, "previous_value":   4.10, "delta_pct": 0.00},
        "SPX":   {"symbol": "SPX",   "current_value": 5100.0, "previous_value": 5100.0, "delta_pct": 0.00},
    }

    def get_snapshots(self) -> Dict[str, Any]:
        return {k: dict(v) for k, v in self.SNAPSHOTS.items()}


class RealProxyProvider(ProxyProvider):
    """
    Stub for a real market-data provider (e.g. Twelve Data, Yahoo Finance).
    Raises NotImplementedError until properly implemented.
    Safe: calling code must handle this and fail-closed.
    """

    def get_snapshots(self) -> Dict[str, Any]:
        raise NotImplementedError(
            "RealProxyProvider is not yet implemented. "
            "Set PROXY_PROVIDER=mock to use the mock provider, "
            "or implement RealProxyProvider.get_snapshots()."
        )


def get_proxy_provider() -> ProxyProvider:
    """
    Factory: select provider from PROXY_PROVIDER env var.
    Defaults to 'mock' so CI never makes external calls.
    """
    choice = os.getenv("PROXY_PROVIDER", "mock").lower()
    if choice == "mock":
        logger.info("ProxyProvider: using MockProxyProvider (deterministic).")
        return MockProxyProvider()
    if choice == "real":
        logger.warning(
            "ProxyProvider: RealProxyProvider selected but not implemented. "
            "System will fail-closed on data requests."
        )
        return RealProxyProvider()
    raise ValueError(f"Unknown PROXY_PROVIDER value: {choice!r}. Expected 'mock' or 'real'.")
