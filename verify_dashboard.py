import sys
import os

sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient
from services.dashboard.main import app
import traceback

client = TestClient(app)
os.environ["DASHBOARD_AUTH_ENABLED"] = "false" # bypass auth for test

routes_to_test = [
    "/dashboard",
    "/dashboard/ops/daily",
    "/dashboard/ops/weekly",
    "/dashboard/execution-prep",
    "/dashboard/health",
    "/dashboard/queue",
    "/dashboard/trades",
    "/dashboard/pilot",
    "/dashboard/fundamentals"
]

failed = False
for route in routes_to_test:
    try:
        response = client.get(route)
        if response.status_code == 200:
            print(f"PASS: {route} (200 OK)")
        else:
            print(f"FAIL: {route} returned {response.status_code}")
            failed = True
    except Exception as e:
        print(f"CRASH: {route} threw an exception:")
        traceback.print_exc()
        failed = True

if failed:
    sys.exit(1)
else:
    print("ALL ROUTES PASSED!")
    sys.exit(0)
