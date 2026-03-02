from abc import ABC, abstractmethod
from typing import Dict, Any
import random


class ProxyProvider(ABC):
    @abstractmethod
    def get_snapshots(self) -> Dict[str, Any]:
        """Return a dictionary of market proxy snapshots with historical context."""
        pass


class MockProxyProvider(ProxyProvider):
    def __init__(self):
        # Initialize some baseline values
        self.history = {"DXY": 103.50, "US10Y": 4.10, "SPX": 5100.0}

    def get_snapshots(self) -> Dict[str, Any]:
        """Generate mock data testing deltas for DXY, US10Y, and SPX."""
        result = {}
        for sym, prev in self.history.items():
            # Random walk +/- max 1.5%
            change_pct = random.uniform(-1.5, 1.5)
            curr = prev * (1 + change_pct / 100)

            # Ensure sensible rounding
            curr = round(curr, 2 if sym != "SPX" else 1)

            result[sym] = {
                "symbol": sym,
                "current_value": curr,
                "previous_value": prev,
                "delta_pct": round(change_pct, 2),
            }

            # Update history for next tick
            self.history[sym] = curr

        return result
