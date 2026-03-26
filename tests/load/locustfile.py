from locust import HttpUser, task, between
import random

class TradingSystemUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def view_jarvis(self):
        self.client.get("/api/jarvis")

    @task(2)
    def list_tickets(self):
        self.client.get("/api/tickets?state=OPEN")

    @task(1)
    def health_check(self):
        self.client.get("/health")
