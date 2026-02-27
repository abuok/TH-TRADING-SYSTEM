#!/bin/bash
# scripts/smoke_test.sh
# Validates production health endpoints and basic flow

echo "=== PHX Production Smoke Test ==="

# Check Dashboard (expect 401 if auth on, 200 if off)
echo "Checking Dashboard health..."
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/dashboard)
if [ "$STATUS_CODE" -eq 401 ] || [ "$STATUS_CODE" -eq 200 ]; then
    echo "OK: Dashboard reachable (Status $STATUS_CODE)"
else
    echo "ERROR: Dashboard unreachable (Status $STATUS_CODE)"
    exit 1
fi

# Check Metrics
echo "Checking Orchestration metrics..."
if curl -s http://localhost:8003/metrics | grep -q "tickets_generated_total"; then
    echo "OK: Metrics reachable and exposing telemetry"
else
    echo "ERROR: Metrics missing or unreachable"
    exit 1
fi

echo "=== Smoke Test Passed ==="
