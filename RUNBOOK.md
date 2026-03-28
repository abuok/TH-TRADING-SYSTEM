# TH Trading System v1.3 - Operational Runbook

## Overview
This runbook defines the standard operating procedures for the TH Trading System v1.3 cluster. It covers cluster instantiation, critical alerts, fail-safe mechanisms, and recovery procedures introduced during the Reliability Hardening phase.

---

## 🚀 1. Cluster Instantiation & Startup
The architectural standardization means all 8 services (Ports 8001-8008) must be brought up together. 

### Standard Startup
```bash
docker-compose up -d --build
```
This single command orchestrates:
1. `redis` & `postgres` (Infrastructure Layer)
2. `bridge` (Ingestion Gateway)
3. Core Logic Nodes (`ingestion`, `technical`, `risk`, `journal`, `orchestration`, `research`)
4. UI Node (`dashboard`)

### Health Verification
Navigate to `http://localhost:8005/dashboard` to view the Command Center. Ensure all 8 service indicators show **ONLINE**. If any node shows OFFLINE, click the module to inspect its localized Trace ID and error JSON.

---

## 🚨 2. Critical Alerts & Responses
The v1.3 system introduces standard `TradingSystemError` JSON schemas. Here's how to respond to the new automated safety trips.

### A. STALE_DATA_OUTAGE
**Trigger**: The Technical Worker has not received a `LiveQuote` or `PriceQuote` update over the Redis EventBus for >300 seconds.
**System Action**: `TechnicalWorker` will force-invalidate all active `PHXDetector` state machines back to `IDLE`.
**Human Response**:
1. Check the MT5 Bridge (`localhost:8008/health`). Is the terminal disconnected?
2. If the market is closed (weekend), this alert is normal. No action required.
3. If the market is open, restart the bridge: `docker-compose restart bridge`. 

### B. EVENTBUS_BLACKOUT
**Trigger**: A worker fails to connect to the Redis EventBus (3 consecutive connection failures).
**System Action**: Graceful Degradation. The worker logs `CRITICAL` but does not crash. It suspends internal message publishing until Redis is reachable again.
**Human Response**:
1. Verify Redis Docker container health: `docker logs th_redis`
2. Usually indicative of an OOM kill on the Redis node. Check host memory. Restart Redis: `docker-compose restart redis`.

### C. RISK_CAP_REACHED
**Trigger**: Daily or Total absolute percentage loss thresholds are breached on the connected account.
**System Action**: The `LockoutEngine` permanently denies all pending validations from the `RiskWorker`.
**Human Response**:
1. This is a severe operational trip designed to prevent account decimation.
2. DO NOT bypass manually unless explicitly approved by the Lead Quant.
3. To reset for the next trading day, no action is needed (automatically expires at rollover timezone).

---

## 📈 3. Observability & Debugging

**Distributed Tracing**
All requests moving from `bridge -> technical -> risk -> orchestrator` carry an `X-B3-TraceId` injected by the v1.3 OpenTelemetry middleware.
* To debug a rejected order, grep the initial bridge ingest `TraceId` across all container logs.
```bash
docker-compose logs | grep "INSERT_TRACE_ID_HERE"
```

**Force Emergency Stop**
If a logic bug is rapidly executing bad trades:
```bash
docker stop $(docker ps -a -q --filter ancestor=th_orchestration)
```
Stopping the `Orchestration` service acts as an immediate physical kill-switch, as no setups can be transformed into live orders.
