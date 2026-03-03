# Functional Spec Snapshot (v1.0.0 Baseline)

This document serves as the canonical reference for the TH Trading System v1.0.0 functionality, extracted from original documentation and walkthroughs.

## 1. Subsystem Requirements

### Ingestion & Market Context
- **MarketContext**: Produces packets containing scheduled events and "no-trade" windows.
- **Proxies**: Ingests US10Y and DXY data (Real/Mock) for macro alignment.
- **Health**: Must monitor provider latency and staleness.

### Fundamentals
- **Bias Packets**: Produces deterministic `PairFundamentals` objects based on processed intel.
- **Regime Detection**: Bridges fundamental bias with technical execution windows.

### Technical Scanner
- **PHX Model**: Tracks stage progression (e.g., Stage 1 to 3) and scores setups.
- **Signals**: Emits `technical_setups` to the event bus.

### Guardrails & Risk
- **Precedence**: Guardrail `hard_block` MUST override any Risk Engine `ALLOW`.
- **Risk Engine**: Evaluates Risk/Reward (RR), session drawdown limits, and news event windows.
- **Safety**: Subscribes to `market_context` and `technical_setups` to emit `risk_approvals`.

### Tickets & Manual Review Queue
- **Non-Executing**: Tickets are data objects only.
- **Lifecycle**: Supports `approve`, `skip`, `expire`, `close`.
- **Workflow**: Human-in-the-loop review via the Dashboard Queue.

### Execution Prep
- **Data-Only**: Prepares entry parameters but DOES NOT trigger orders.
- **Fail-Closed**: Must fail if live quotes or symbol specs are missing/stale.

### Trade Capture & Management
- **Capture**: READ-ONLY ingestion of MT5 fills and positions. No `OrderSend` capability.
- **Management Assistant**: Provides suggestions (Move SL, TP1) but does not modify broker orders.

### Research, Pilot & Tuning
- **Hindsight**: Deterministic simulation of missed vs. realized outcomes.
- **Pilot Gate**: Hard thresholds for graduation (Staleness < 30s, Expectancy > 0.05R, etc.).
- **Tuning**: Weekly parameter suggestions based on historical data.

### Ops & Hardening
- **Reports**: Daily and Weekly Ops reports generated from system logs.
- **Hardening**: Required Auth for dashboard, DB backups, and fail-closed providers in `ENV=prod`.

## 2. Safety Invariants
- **NO BROKER EXECUTION**: All paths leading to `OrderSend` or trading API calls are forbidden.
- **FAIL-CLOSED**: Missing providers or stale data in production must halt ticket generation.
- **IDEMPOTENCY**: Duplicate events must not result in duplicate tickets or journal entries.
- **TIMEZONE**: Internal storage in `UTC`; Display in `Africa/Nairobi`.

## 3. Operator UX
- **Dashboard**: All routes (`/ops`, `/queue`, `/tickets`, etc.) must be available and readable.
- **Alerting**: Critical failures (Kill Switch, Risk Block) must trigger notifications.
