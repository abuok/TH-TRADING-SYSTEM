# End-to-End Demo Guide (V1)

This guide explains how to run the full trading system stack and verify the core pipeline from data ingestion to journaling.

## Overview
The E2E Demo simulates a complete trading session:
1. **Services Start**: Docker Compose brings up PostgreSQL, Redis, and all microservices.
2. **Pre-session Briefing**: The Orchestrator analyzes historical data to establish bias.
3. **Live Monitoring**: The system scans for technical setups in a simulated loop.
4. **Risk Evaluation**: Detected setups are routed to the Risk Engine for approval.
5. **Journaling**: Decisions and outcomes are logged for auditing.
6. **Reporting**: An HTML daily summary is generated.

## Prerequisites
- Docker & Docker Compose
- Python 3.10+
- `make` utility

## Running the Demo

### 1. Set Up Environment
Ensure your `.env` file is configured (copy from `.env.example`).
```bash
make install
```

### 2. Execute Demo
```bash
make demo
```

### 3. Expected Output
You should see colored console notifications from the `ConsoleNotificationAdapter`:
- `[INFO] Trading Session Started: run_...`
- `[INFO] Setup Forming on BTCUSD: Score 60.0`
- `[SUCCESS] Setup Execute-Ready on BTCUSD`
- `[ERROR] Risk BLOCK on BTCUSD: Low RR` (if conditions not met)
- `[SUCCESS] E2E Demo Complete. Report Ready.`

### 4. Verify Results
- **HTML Report**: Check `artifacts/daily_report.html` for the performance summary.
- **Database**: Use `make cli-packets` to view persisted decision packets in the DB.

## Automated Acceptance Tests
To run the E2E flow in a headless, fast mode without Docker:
```bash
python -m pytest services/orchestration/tests/test_e2e.py
```
This test uses in-memory SQLite and mocks to verify the logic remains deterministic.
