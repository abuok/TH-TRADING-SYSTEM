"""
shared/logic/metrics.py
-----------------------
Production-grade Prometheus-compatible metrics registry for the TH Trading System.

Supports:
  - Counters  (monotonically increasing)
  - Gauges    (point-in-time values, can decrease)
  - Histograms (latency / distribution buckets)

Usage::

    from shared.logic.metrics import metrics_registry

    # Counter
    metrics_registry.increment("tickets_generated_total")
    metrics_registry.increment("incidents_total", label="CRITICAL")

    # Gauge
    metrics_registry.set_gauge("active_positions", 3)
    metrics_registry.inc_gauge("open_tickets")
    metrics_registry.dec_gauge("open_tickets")

    # Histogram (records a duration in seconds)
    metrics_registry.observe("http_request_duration_seconds", 0.042,
                             labels={"endpoint": "/dashboard"})

The ``/metrics`` endpoint in each service returns the Prometheus text
exposition format, compatible with ``prometheus_client``-scrapers.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class MetricsRegistry:
    """
    Thread-safe singleton metrics registry.

    Counters, gauges, and histograms are stored in-memory and serialised
    to Prometheus text format on demand via :meth:`get_metrics_text`.
    """

    _instance: "MetricsRegistry | None" = None
    _lock = threading.Lock()

    # Default histogram bucket boundaries (seconds / generic)
    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __new__(cls) -> "MetricsRegistry":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._counters: dict[str, dict[str, float] | float] = {}
                inst._gauges: dict[str, float] = {}
                inst._histograms: dict[str, dict[str, Any]] = {}
                inst._meta: dict[str, dict[str, str]] = {}      # {name: {help, type}}
                cls._instance = inst
                inst._init_defaults()
        return cls._instance  # type: ignore[return-value]

    # ─── Initialise well-known metrics ───────────────────────────────────────

    def _init_defaults(self) -> None:
        # Business counters
        self._define("packets_processed_total",    "counter", "Total packets processed")
        self._define("tickets_generated_total",    "counter", "Total order tickets generated")
        self._define("tickets_approved_total",     "counter", "Total tickets approved by operator")
        self._define("tickets_skipped_total",      "counter", "Total tickets skipped by operator")
        self._define("tickets_closed_total",       "counter", "Total tickets closed with outcome")
        self._define("tickets_rejected_jit_total", "counter", "Tickets rejected by JIT validator")
        self._define("incidents_total",            "counter", "Incidents logged by severity label")
        self._define("policy_switches_total",      "counter", "Policy selection events")
        self._define("queue_decisions_total",      "counter", "Queue decisions by action label")
        self._define("hindsight_computations_total","counter","Hindsight R computations")
        self._define("audit_actions_total",        "counter", "Audit trail entries written")
        self._define("rate_limit_hits_total",      "counter", "Requests rejected by rate limiter")
        self._define("alignment_evaluations_total","counter", "Alignment engine evaluations")
        self._define("briefings_generated_total",  "counter", "Session briefings generated")
        self._define("trade_fills_processed_total","counter", "Trade fill events processed by bridge")

        # System gauges
        self._define("open_tickets_count",         "gauge",   "Current tickets in IN_REVIEW status")
        self._define("active_positions_count",     "gauge",   "Broker positions currently open")
        self._define("db_pool_available",          "gauge",   "Database connection pool available connections")
        self._define("db_pool_checked_out",        "gauge",   "Database connection pool checked-out connections")

        # Performance histograms
        self._define("http_request_duration_seconds",  "histogram", "HTTP endpoint latency")
        self._define("db_query_duration_seconds",      "histogram", "Database query latency")
        self._define("ticket_approval_duration_seconds","histogram","Time from ticket creation to approval")

        # Initialise counter zero-values
        for name, meta in self._meta.items():
            if meta["type"] == "counter" and name not in self._counters:
                self._counters[name] = 0.0

    def _define(self, name: str, metric_type: str, help_text: str) -> None:
        self._meta[name] = {"type": metric_type, "help": help_text}

    # ─── Counter API ─────────────────────────────────────────────────────────

    def increment(self, name: str, label: str | None = None, amount: float = 1.0) -> None:
        with self._lock:
            if label:
                if name not in self._counters or not isinstance(self._counters[name], dict):
                    self._counters[name] = {}
                entry = self._counters[name]
                assert isinstance(entry, dict)
                entry[label] = entry.get(label, 0.0) + amount
            else:
                current = self._counters.get(name, 0.0)
                self._counters[name] = (current if isinstance(current, (int, float)) else 0.0) + amount

    # ─── Gauge API ───────────────────────────────────────────────────────────

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def inc_gauge(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._gauges[name] = self._gauges.get(name, 0.0) + amount

    def dec_gauge(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._gauges[name] = max(0.0, self._gauges.get(name, 0.0) - amount)

    # ─── Histogram API ───────────────────────────────────────────────────────

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a single observation into a histogram bucket."""
        label_key = self._labels_key(labels)
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {}
            if label_key not in self._histograms[name]:
                self._histograms[name][label_key] = {
                    "buckets": defaultdict(int),
                    "sum": 0.0,
                    "count": 0,
                    "labels": labels or {},
                }
            entry = self._histograms[name][label_key]
            entry["sum"] += value
            entry["count"] += 1
            for b in self.DEFAULT_BUCKETS:
                if value <= b:
                    entry["buckets"][b] += 1
            entry["buckets"]["+Inf"] = entry["count"]

    @staticmethod
    def _labels_key(labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    # ─── Context manager for timing ──────────────────────────────────────────

    def time(self, name: str, labels: dict[str, str] | None = None):
        """Use as a context manager to time a block and record to histogram."""
        return _Timer(self, name, labels)

    # ─── Prometheus text exposition ──────────────────────────────────────────

    def get_metrics_text(self) -> str:
        lines: list[str] = []
        with self._lock:
            # Counters
            for name, value in self._counters.items():
                meta = self._meta.get(name, {})
                lines.append(f'# HELP {name} {meta.get("help", "")}')
                lines.append(f'# TYPE {name} counter')
                if isinstance(value, dict):
                    for label, count in value.items():
                        lines.append(f'{name}{{label="{label}"}} {count}')
                else:
                    lines.append(f"{name} {value}")

            # Gauges
            for name, value in self._gauges.items():
                meta = self._meta.get(name, {})
                lines.append(f'# HELP {name} {meta.get("help", "")}')
                lines.append(f'# TYPE {name} gauge')
                lines.append(f"{name} {value}")

            # Histograms
            for name, label_entries in self._histograms.items():
                meta = self._meta.get(name, {})
                lines.append(f'# HELP {name} {meta.get("help", "")}')
                lines.append(f'# TYPE {name} histogram')
                for _, entry in label_entries.items():
                    label_str = self._labels_key(entry["labels"])
                    prefix = f'{{{label_str}}}' if label_str else ""
                    for b, cnt in sorted(
                        entry["buckets"].items(),
                        key=lambda x: float("inf") if x[0] == "+Inf" else float(x[0]),
                    ):
                        bucket_label = f'le="{b}"'
                        if label_str:
                            bucket_label = f'{label_str},{bucket_label}'
                        lines.append(f'{name}_bucket{{{bucket_label}}} {cnt}')
                    lines.append(f'{name}_sum{prefix} {entry["sum"]}')
                    lines.append(f'{name}_count{prefix} {entry["count"]}')

        return "\n".join(lines)

    # ─── Snapshot (for tests / health checks) ────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histogram_counts": {
                    name: {k: v["count"] for k, v in entries.items()}
                    for name, entries in self._histograms.items()
                },
            }


class _Timer:
    """Context manager returned by :meth:`MetricsRegistry.time`."""

    def __init__(self, registry: MetricsRegistry, name: str, labels: dict[str, str] | None) -> None:
        self._registry = registry
        self._name = name
        self._labels = labels
        self._start = 0.0

    def __enter__(self) -> "_Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        elapsed = time.perf_counter() - self._start
        self._registry.observe(self._name, elapsed, self._labels)


metrics_registry = MetricsRegistry()
