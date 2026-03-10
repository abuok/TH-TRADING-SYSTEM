#!/bin/bash
# scripts/smoke_test.sh
# Validates production health endpoints and basic flow
# Port mapping (docker-compose):
#   ingestion=8001, technical=8002, risk=8003, journal=8004
#   dashboard=8005, orchestration=8006

echo "=== PHX Production Smoke Test ==="

# Check Dashboard
echo "Checking Dashboard health..."
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/dashboard)
if [ "$STATUS_CODE" -eq 401 ] || [ "$STATUS_CODE" -eq 200 ]; then
    echo "OK: Dashboard reachable (Status $STATUS_CODE)"
else
    echo "ERROR: Dashboard unreachable (Status $STATUS_CODE)"
    exit 1
fi

# Check Orchestration Metrics (port 8006)
echo "Checking Orchestration metrics..."
if curl -s http://localhost:8006/metrics | grep -q "tickets_generated_total"; then
    echo "OK: Metrics reachable and exposing telemetry"
else
    echo "ERROR: Metrics missing or unreachable"
    exit 1
fi

echo "=== Smoke Test Passed ==="
