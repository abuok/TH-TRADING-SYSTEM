from typing import Dict, Any, List
from datetime import datetime
import threading

class MetricsRegistry:
    """
    Simple in-memory metrics registry for Prometheus-style reporting.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MetricsRegistry, cls).__new__(cls)
                cls._instance._metrics = {
                    "packets_processed_total": 0,
                    "tickets_generated_total": 0,
                    "incidents_total": {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0},
                    "policy_switches_total": 0,
                    "queue_decisions_total": {"APPROVE": 0, "SKIP": 0},
                    "hindsight_computations_total": 0,
                }
        return cls._instance

    def increment(self, name: str, label: str = None):
        with self._lock:
            if label:
                if name not in self._metrics:
                    self._metrics[name] = {}
                self._metrics[name][label] = self._metrics[name].get(label, 0) + 1
            else:
                self._metrics[name] = self._metrics.get(name, 0) + 1

    def get_metrics_text(self) -> str:
        """Returns Prometheus formatted metrics text."""
        lines = []
        with self._lock:
            for name, value in self._metrics.items():
                if isinstance(value, dict):
                    for label, count in value.items():
                        lines.append(f'{name}{{label="{label}"}} {count}')
                else:
                    lines.append(f"{name} {value}")
        return "\n".join(lines)

metrics_registry = MetricsRegistry()
