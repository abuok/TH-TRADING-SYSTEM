from abc import ABC, abstractmethod
import logging
from typing import List

logger = logging.getLogger("Notifications")

class NotificationAdapter(ABC):
    @abstractmethod
    def send(self, message: str, level: str = "INFO"):
        pass

class ConsoleNotificationAdapter(NotificationAdapter):
    def send(self, message: str, level: str = "INFO"):
        color = ""
        reset = "\033[0m"
        if level == "SUCCESS": color = "\033[92m" # Green
        elif level == "WARNING": color = "\033[93m" # Yellow
        elif level == "ERROR": color = "\033[91m" # Red
        elif level == "INFO": color = "\033[94m" # Blue
        
        print(f"{color}[{level}] {message}{reset}")

class NotificationService:
    def __init__(self, adapters: List[NotificationAdapter]):
        self.adapters = adapters

    def notify(self, message: str, level: str = "INFO"):
        for adapter in self.adapters:
            try:
                adapter.send(message, level)
            except Exception as e:
                logger.error(f"Failed to send notification via {adapter.__class__.__name__}: {e}")

# Global singleton or helper
_service = NotificationService([ConsoleNotificationAdapter()])
_last_notified = {}

def notify_suggestion(suggestion: dict):
    """Notify about a trade management suggestion with 1h rate limit per ticket+type."""
    from datetime import datetime, timedelta
    ticket_id = suggestion.get("ticket_id")
    s_type = suggestion.get("suggestion_type")
    key = f"{ticket_id}_{s_type}"
    now = datetime.now()
    
    if key in _last_notified:
        if now - _last_notified[key] < timedelta(hours=1):
            return 
            
    _last_notified[key] = now
    msg = (
        f"TRADE MANAGEMENT ALERT: {suggestion.get('symbol')} {s_type} "
        f"({suggestion.get('current_r', 0):.2f}R). "
        f"Instruction: {suggestion.get('instruction')}"
    )
    _service.notify(msg, "WARNING" if "MOVE_SL" in s_type else "ERROR")
