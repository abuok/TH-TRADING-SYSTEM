# Functional Spec Snapshot (v1.0.0 Baseline)

This document serves as the canonical reference for the v1.0.0 functionality, 
extracted from original documentation and walkthroughs.

## 1. Subsystem Requirements

### Ingestion & Market Context

- **MarketContext**: Produces packets for scheduled events and "no-trade" windows.
- **Proxies**: Ingests US10Y and DXY data (Real/Mock) for macro alignment.
- **Health**: Must monitor provider latency and staleness.

### Fundamentals

- **Bias Packets**: Produces deterministic `PairFundamentals` objects.
- **Regime Detection**: Bridges bias with technical execution windows.

### Technical Scanner

- **PHX Model**: Tracks stage progression (Stage 1 to 3) and scores setups.
- **Signals**: Emits `technical_setups` to the event bus.

### Guardrails & Risk

- **Precedence**: Guardrail `hard_block` MUST override any Risk Engine `ALLOW`.
- **Risk Engine**: Evaluates RR, session drawdown, and news event windows.
- **Safety**: Subscribes to events to emit `risk_approvals`.

### Tickets & Manual Review Queue

- **Non-Executing**: Tickets are data objects only.
- **Lifecycle**: Supports `approve`, `skip`, `expire`, `close`.
- **Workflow**: Human-in-the-loop review via the Dashboard Queue.

### Execution Prep

- **Data-Only**: Prepares entry parameters but DOES NOT trigger orders.
- **Fail-Closed**: Must fail if live data or symbol specs are missing/stale.

### Trade Capture & Management

- **Capture**: READ-ONLY ingestion of MT5 fills/positions. No `OrderSend`.
- **Management Assistant**: Rule-based suggestions (Move SL, TP1).

### Research, Pilot & Tuning

- **Hindsight**: Deterministic simulation of missed vs. realized outcomes.
- **Pilot Gate**: Hard thresholds (Staleness < 30s, Expectancy > 0.05R).
- **Tuning**: Weekly parameter suggestions based on historical data.

### Ops & Hardening

- **Reports**: Daily and Weekly Ops reports generated from system logs.
- **Hardening**: Required Auth, DB backups, and fail-closed in `ENV=prod`.

## 2. Safety Invariants

- **NO BROKER EXECUTION**: All trading API calls are strictly forbidden.
- **FAIL-CLOSED**: Missing providers or stale data must halt generation.
- **IDEMPOTENCY**: Duplicate events must not result in duplicate tickets.
- **TIMEZONE**: Internal storage in `UTC`; Display in `Africa/Nairobi`.

## 3. Operator UX

- **Dashboard**: All routes (`/ops`, `/queue`, etc.) must be readable.
- **Alerting**: Critical failures must trigger notifications.
