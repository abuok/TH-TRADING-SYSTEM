from datetime import datetime, time

import pytz

from shared.types.packets import Candle


class SessionEngine:
    # Legacy ranges for backward compatibility during alignment
    ASIA_RANGE = (time(3, 0), time(12, 0))
    LONDON_RANGE = (time(11, 0), time(20, 0))
    NY_RANGE = (time(16, 0), time(1, 0))

    @staticmethod
    def is_in_range(t: time, start: time, end: time) -> bool:
        if start <= end:
            return start <= t <= end
        else:  # Crosses midnight
            return t >= start or t <= end

    @classmethod
    def get_session_candles(
        cls, candles: list[Candle], session_range: tuple[time, time]
    ) -> list[Candle]:
        start, end = session_range
        session_candles = []
        nairobi_tz = pytz.timezone("Africa/Nairobi")
        for candle in candles:
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
    def get_high_low(cls, candles: list[Candle]) -> dict[str, float]:
        if not candles:
            return {}
        return {
            "high": max(c.high for c in candles),
            "low": min(c.low for c in candles),
        }

    @classmethod
    def compute_all_levels(cls, candles: list[Candle]) -> dict[str, float]:
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

    @classmethod
    def get_session_state(cls, now_nairobi: datetime, asset_pair: str) -> str:
        t = now_nairobi.time()

        # Shared windows
        if cls.is_in_range(t, time(7, 0), time(10, 59)):
            return "PRE_SESSION"
        if cls.is_in_range(t, time(11, 0), time(13, 59)):
            return "LONDON_OPEN"
        if cls.is_in_range(t, time(14, 0), time(15, 59)):
            return "LONDON_MID"
        if cls.is_in_range(t, time(16, 0), time(18, 59)):
            return "NY_OPEN"
        if cls.is_in_range(t, time(19, 0), time(21, 59)):
            return "POST_SESSION"

        # Instrument specific
        if cls.is_in_range(t, time(3, 0), time(6, 59)):
            if asset_pair == "GBPJPY":
                return "ASIA_SESSION"
            # For XAUUSD and others, Asia is effectively OUT_OF_SESSION
            return "OUT_OF_SESSION"

        # Catch-all
        return "OUT_OF_SESSION"


def get_nairobi_time() -> datetime:
    """Returns the current time in Africa/Nairobi."""
    return datetime.now(pytz.timezone("Africa/Nairobi"))


def get_session_label(now_nairobi: datetime, asset_pair: str = "UNKNOWN") -> str:
    """Wrapper mapping to SessionEngine.get_session_state."""
    return SessionEngine.get_session_state(now_nairobi, asset_pair)
