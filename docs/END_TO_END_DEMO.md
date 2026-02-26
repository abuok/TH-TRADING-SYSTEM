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

## Failure-Mode Simulations (Hardening V1)

### 1. Kill Switch Simulation
To halt all operations across the stack:
```bash
python infra/cli.py kill-switch set HALT_ALL
```
Observe the Orchestrator/Services logs indicating `HALTED by kill switch`. To resume:
```bash
python infra/cli.py kill-switch unset HALT_ALL
```

### 2. Service-Specific Halt
To stop only the Orchestrator:
```bash
python infra/cli.py kill-switch set HALT_SERVICE --target Orchestrator
```

### 3. Stale Packet Guard
The Orchestrator will automatically reject packets older than their TTL (e.g., 30s for MarketContext). 
Verify this by stopping the Ingestion service while keeping the Orchestrator running. After 30s, the Orchestrator will log `Abandoning loop iteration ... due to stale context` and log an `IncidentLog` in the DB.

### 4. Health Checks
Check the status of any service:
```bash
curl http://localhost:8001/health  # Ingestion
curl http://localhost:8004/health  # Journal
```

## Automated Hardening Tests
To verify all reliability features (kill switches, staleness, idempotency):
```bash
python -m pytest services/orchestration/tests/test_hardening.py
```
