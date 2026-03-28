import random
from locust import HttpUser, task, between

# The services run on ports 8001 through 8008
SERVICE_PORTS = [8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008]

class TradingSystemUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Choose a random service for this user instance if host is not provided
        self.port = random.choice(SERVICE_PORTS)
        if not self.host:
            self.host = f"http://127.0.0.1:{self.port}"

    @task(3)
    def check_health(self):
        """Simulate monitoring probes."""
        self.client.get("/health", name=f"GET /health (Port {self.port})")

    @task(2)
    def check_metrics(self):
        """Simulate Prometheus scraping."""
        self.client.get("/metrics", name=f"GET /metrics (Port {self.port})")

    @task(1)
    def simulate_quote_ingestion(self):
        """Simulate high-frequency quote ingestion if hitting the Bridge."""
        if self.port == 8008:
            payload = {
                "symbol": "XAUUSD",
                "bid": 2000.0 + random.uniform(-0.5, 0.5),
                "ask": 2000.1 + random.uniform(-0.5, 0.5),
                "timestamp": "2023-10-27T10:00:00Z"
            }
            self.client.post("/bridge/quote", json=payload, name="POST /bridge/quote")
        else:
            # Just do a health check if not on bridge
            self.check_health()
