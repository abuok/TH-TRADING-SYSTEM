"""
shared/logic/candle_aggregator.py
Aggregates raw quote streams into OHLCV candles (1M, 5M, 15M, etc.).
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from shared.types.packets import Candle

class CandleAggregator:
    """
    Manages building candles for multiple symbols and timeframes.
    In-memory state for performance; persistence handled by consumers.
    """
    def __init__(self, timeframes: List[str] = ["1m", "5m", "15m"]):
        self.timeframes = timeframes
        # State: {symbol: {timeframe: current_candle_obj}}
        self.state: Dict[str, Dict[str, Optional[dict]]] = {}

    def _get_round_time(self, dt: datetime, timeframe: str) -> datetime:
        """Rounds a datetime down to the nearest timeframe interval."""
        if timeframe.endswith("m"):
            minutes = int(timeframe[:-1])
            return dt.replace(minute=(dt.minute // minutes) * minutes, second=0, microsecond=0)
        elif timeframe.endswith("h"):
            hours = int(timeframe[:-1])
            return dt.replace(hour=(dt.hour // hours) * hours, minute=0, second=0, microsecond=0)
        return dt.replace(second=0, microsecond=0)

    def update(self, symbol: str, bid: float, ask: float, ts: datetime = None) -> List[Candle]:
        """
        Updates internal state with a new quote.
        Returns any COMPLETED candles.
        """
        if ts is None:
            ts = datetime.now(timezone.utc)
        
        price = (bid + ask) / 2.0
        completed = []

        if symbol not in self.state:
            self.state[symbol] = {tf: None for tf in self.timeframes}

        for tf in self.timeframes:
            round_ts = self._get_round_time(ts, tf)
            current = self.state[symbol][tf]

            if current is None:
                # First candle for this tf
                self.state[symbol][tf] = {
                    "timestamp": round_ts,
                    "open": price, "high": price, "low": price, "close": price,
                    "volume": 1.0
                }
            elif round_ts > current["timestamp"]:
                # Current candle finished, start new one
                completed.append(Candle(**current))
                self.state[symbol][tf] = {
                    "timestamp": round_ts,
                    "open": price, "high": price, "low": price, "close": price,
                    "volume": 1.0
                }
            else:
                # Update current candle
                current["high"] = max(current["high"], price)
                current["low"] = min(current["low"], price)
                current["close"] = price
                current["volume"] += 1.0
        
        return completed
