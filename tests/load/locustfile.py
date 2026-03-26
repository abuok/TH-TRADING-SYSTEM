"""
tests/load/locustfile.py
------------------------
Locust load testing suite for TH-TRADING-SYSTEM.

Run (headless CI mode):
    locust -f tests/load/locustfile.py \
        --headless -u 50 -r 10 -t 5m \
        --host http://localhost:8000 \
        --csv=tests/load/results/baseline

Run (interactive UI):
    locust -f tests/load/locustfile.py --host http://localhost:8000
    # Open http://localhost:8089
"""

from __future__ import annotations

import random
from locust import HttpUser, between, events, task


PAIRS = ["XAUUSD", "GBPJPY", "EURUSD"]
BIASES = ["BUY", "SELL"]


class DashboardUser(HttpUser):
    """Simulate an operator monitoring the dashboard."""

    wait_time = between(2, 5)

    @task(10)
    def view_command_center(self) -> None:
        self.client.get("/dashboard", name="/dashboard")

    @task(5)
    def view_order_flow(self) -> None:
        self.client.get("/dashboard/order-flow", name="/dashboard/order-flow")

    @task(3)
    def view_strategy_context(self) -> None:
        self.client.get(
            "/dashboard/strategy-context", name="/dashboard/strategy-context"
        )

    @task(2)
    def view_node_telemetry(self) -> None:
        self.client.get(
            "/dashboard/node-telemetry", name="/dashboard/node-telemetry"
        )

    @task(1)
    def health_check(self) -> None:
        self.client.get("/health", name="/health")


class APIUser(HttpUser):
    """Simulate internal service-to-service API traffic."""

    wait_time = between(0.5, 2)

    @task(5)
    def check_health(self) -> None:
        self.client.get("/health", name="/health")

    @task(3)
    def get_metrics(self) -> None:
        self.client.get("/metrics", name="/metrics")


# ── Result listener ───────────────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:  # type: ignore[type-arg]
    print("\n[LOCUST] Load test started — warming up...")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:  # type: ignore[type-arg]
    stats = environment.stats.total
    print("\n========== LOAD TEST RESULTS ==========")
    print(f"  Total requests  : {stats.num_requests}")
    print(f"  Failed requests : {stats.num_failures}")
    print(f"  Failure rate    : {stats.fail_ratio * 100:.1f}%")
    print(f"  Avg resp time   : {stats.avg_response_time:.0f}ms")
    print(f"  P50             : {stats.get_response_time_percentile(0.50):.0f}ms")
    print(f"  P95             : {stats.get_response_time_percentile(0.95):.0f}ms")
    print(f"  P99             : {stats.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Max             : {stats.max_response_time:.0f}ms")
    print("=======================================\n")

    # Fail the CI step if p95 > 2s or failure rate > 1%
    if stats.get_response_time_percentile(0.95) > 2000:
        raise SystemExit("FAIL: p95 response time exceeded 2000ms")
    if stats.fail_ratio > 0.01:
        raise SystemExit(f"FAIL: failure rate {stats.fail_ratio * 100:.1f}% > 1%")
