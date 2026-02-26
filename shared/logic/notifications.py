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
