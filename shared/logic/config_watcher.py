import json
import logging
import threading
from typing import Any, Callable

from shared.messaging.event_bus import EventBus

logger = logging.getLogger(__name__)

class ConfigWatcher:
    """
    Listens for configuration updates on Redis PubSub and updates a local config dict.
    Allows for live-reloading of risk parameters without service restarts.
    """
    def __init__(self, channel: str = "config_updates"):
        self.channel = channel
        self.event_bus = EventBus()
        self.config_overrides: dict[str, Any] = {}
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, callback: Callable[[dict[str, Any]], None] | None = None):
        """Start the background thread to watch for updates."""
        self._callback = callback
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"ConfigWatcher started on channel: {self.channel}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        pubsub = self.event_bus.client.pubsub()
        pubsub.subscribe(self.channel)
        
        # Initial load from a standard Redis Key (if exists)
        initial_payload = self.event_bus.client.get("system_config_live")
        if initial_payload:
            try:
                self.config_overrides = json.loads(initial_payload)
                if self._callback:
                    self._callback(self.config_overrides)
            except Exception as e:
                logger.error(f"Failed to load initial config: {e}")

        while not self._stop_event.is_set():
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message['type'] == 'message':
                    data = json.loads(message['data'])
                    logger.info(f"Config update received: {data}")
                    self.config_overrides.update(data)
                    if self._callback:
                        self._callback(self.config_overrides)
            except Exception as e:
                logger.error(f"Error in ConfigWatcher loop: {e}")
                
    def get(self, key: str, default: Any = None) -> Any:
        return self.config_overrides.get(key, default)
