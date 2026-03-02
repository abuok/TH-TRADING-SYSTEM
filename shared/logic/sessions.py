from datetime import time, datetime
from typing import List, Dict, Tuple
from shared.types.packets import Candle
import pytz


class TradingSessions:
    # Nairobi is UTC+3
    # Standard Session Ranges (Nairobi Time)
    ASIA_RANGE = (time(3, 0), time(12, 0))
    LONDON_OPEN_WINDOW = (time(11, 0), time(14, 0))
    LONDON_RANGE = (time(11, 0), time(20, 0))
    NY_WINDOW = (time(16, 0), time(19, 0))
    NY_RANGE = (time(16, 0), time(1, 0))  # Note: Crosses midnight

    @staticmethod
    def is_in_range(t: time, start: time, end: time) -> bool:
        if start <= end:
            return start <= t <= end
        else:  # Crosses midnight
            return t >= start or t <= end

    @classmethod
    def get_session_candles(
        cls, candles: List[Candle], session_range: Tuple[time, time]
    ) -> List[Candle]:
        start, end = session_range
        session_candles = []
        nairobi_tz = pytz.timezone("Africa/Nairobi")
        for candle in candles:
            # Explicitly force raw DB/MT5 timestamps into EAT (Nairobi) before comparing
            dt_aware = (
                candle.timestamp
                if candle.timestamp.tzinfo
                else candle.timestamp.replace(tzinfo=pytz.utc)
            )
            t_nairobi = dt_aware.astimezone(nairobi_tz).time()
            if cls.is_in_range(t_nairobi, start, end):
                session_candles.append(candle)
        return session_candles

    @classmethod
    def get_high_low(cls, candles: List[Candle]) -> Dict[str, float]:
        if not candles:
            return {}
        return {
            "high": max(c.high for c in candles),
            "low": min(c.low for c in candles),
        }

    @classmethod
    def compute_all_levels(cls, candles: List[Candle]) -> Dict[str, float]:
        """Compute High/Low for Asia and London sessions."""
        asia_candles = cls.get_session_candles(candles, cls.ASIA_RANGE)
        london_candles = cls.get_session_candles(candles, cls.LONDON_RANGE)

        asia_hl = cls.get_high_low(asia_candles)
        london_hl = cls.get_high_low(london_candles)

        levels = {}
        if asia_hl:
            levels["asia_high"] = asia_hl["high"]
            levels["asia_low"] = asia_hl["low"]
        if london_hl:
            levels["london_high"] = london_hl["high"]
            levels["london_low"] = london_hl["low"]

        return levels


def get_nairobi_time() -> datetime:
    """Returns the current time in Africa/Nairobi."""
    return datetime.now(pytz.timezone("Africa/Nairobi"))


def get_session_label(now_nairobi: datetime) -> str:
    """Returns a label for the current trading session."""
    t = now_nairobi.time()
    if TradingSessions.is_in_range(t, *TradingSessions.LONDON_RANGE):
        return "LONDON"
    if TradingSessions.is_in_range(t, *TradingSessions.NY_RANGE):
        return "NEW YORK"
    if TradingSessions.is_in_range(t, *TradingSessions.ASIA_RANGE):
        return "ASIA"
    return "OUTSIDE"
