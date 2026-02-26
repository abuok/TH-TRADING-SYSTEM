import pytz
from datetime import datetime, time

class SessionManager:
    """
    Manages trading sessions in Africa/Nairobi (UTC+3).
    """
    TIMEZONE = pytz.timezone("Africa/Nairobi")
    
    # Sessions in EAT
    SESSIONS = {
        "LONDON": {"start": time(10, 0), "end": time(19, 0)},
        "NEW_YORK": {"start": time(15, 0), "end": time(23, 59)},
    }

    @classmethod
    def get_current_time_eat(cls) -> datetime:
        return datetime.now(cls.TIMEZONE)

    @classmethod
    def is_in_session(cls) -> bool:
        now_eat = cls.get_current_time_eat().time()
        for session, window in cls.SESSIONS.items():
            if window["start"] <= now_eat <= window["end"]:
                return True
        return False

    @classmethod
    def get_active_sessions(cls) -> list:
        now_eat = cls.get_current_time_eat().time()
        active = []
        for session, window in cls.SESSIONS.items():
            if window["start"] <= now_eat <= window["end"]:
                active.append(session)
        return active
