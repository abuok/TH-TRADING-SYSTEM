from session_manager import SessionManager
from datetime import datetime

def test_session_logic():
    print(f"Current Time (EAT): {SessionManager.get_current_time_eat()}")
    print(f"Is In Session: {SessionManager.is_in_session()}")
    print(f"Active Sessions: {SessionManager.get_active_sessions()}")

    # Mock time test
    mock_eat = SessionManager.TIMEZONE.localize(datetime(2024, 1, 1, 14, 0)) # 2:00 PM EAT
    print(f"Mock 14:00 EAT -> London? {SessionManager.SESSIONS['LONDON']['start'] <= mock_eat.time() <= SessionManager.SESSIONS['LONDON']['end']}")

if __name__ == "__main__":
    test_session_logic()
