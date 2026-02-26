from abc import ABC, abstractmethod
from typing import Dict
import random

class ProxyProvider(ABC):
    @abstractmethod
    def get_snapshots(self) -> Dict[str, float]:
        """Return a dictionary of market proxy snapshots."""
        pass

class MockProxyProvider(ProxyProvider):
    def get_snapshots(self) -> Dict[str, float]:
        """Generate mock data for DXY, US10Y, and SPX."""
        return {
            "DXY": round(random.uniform(101.0, 105.0), 2),
            "US10Y": round(random.uniform(3.5, 4.5), 2),
            "SPX": round(random.uniform(5000.0, 5200.0), 1)
        }
