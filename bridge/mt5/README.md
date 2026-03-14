# PHX Live Bridge EA v2.0

A **read-only** MetaTrader 5 Expert Advisor that streams live market data and trade events to the TH Trading System bridge service. It **never places or modifies orders**.

## What It Does

| Feature            | Endpoint                | Frequency                      |
| ------------------ | ----------------------- | ------------------------------ |
| Quote (bid/ask)    | `POST /bridge/quote`    | Every N seconds (configurable) |
| Symbol Specs       | `POST /bridge/spec`     | On startup                     |
| Position Snapshots | `POST /bridge/trades/*` | Every 30 seconds               |
| Trade Fill Events  | `POST /bridge/trades/*` | On every `OnTrade()` event     |

## Features

- **Data-only**: No order execution logic. Only sends Bid/Ask and Symbol Specs.
- **Configurable Sync**: Adjust sync interval to balance latency vs. bandwidth.
- **Secure**: Uses a secret header to authorize requests to the Bridge service.

## Installation

1. Open MetaTrader 5.
2. Go to `File` -> `Open Data Folder`.
3. Navigate to `MQL5` -> `Experts`.
4. Create a folder named `PHX` and paste `LiveBridgeEA.mq5` into it.
5. In MT5, open the `Navigator` (Ctrl+N), right-click `Experts`, and select `Refresh`.
6. Attach the EA to any chart (e.g., XAUUSD).

## Configuration

When attaching the EA, set the following parameters:

- **Server URL**: The URL where `services/bridge` is running.
- **Bridge Secret**: Must match the `BRIDGE_SECRET` environment variable.
- **Sync Interval**: Seconds between quote syncs (Default: 5).
- **Account ID**: A string identifier for this MT5 account (e.g., `ACC-001`).

## Important: WebRequest Permissions

For the EA to communicate with the Bridge service, you MUST allow the server URL in MT5:

1. Go to `Tools` → `Options` → `Expert Advisors`.
2. Check `Allow WebRequest for listed URL`.
3. Add your Bridge Server URL (e.g., `http://localhost:8005`).

## Order Comment Format (Critical for Ticket Matching)

When placing trades manually in MT5, paste the following into the **Order Comment** field to enable **deterministic matching** between MT5 deals and system tickets:

```text
TICKET:<ticket_id>|PREP:<prep_id>|POLICY:<policy_name>
```

**Example:**

```text
TICKET:TKT-A1B2C3D4|PREP:PREP-X9Y8|POLICY:DEFAULT
```

- `ticket_id` — found on the dashboard Tickets page
- `prep_id` — from the Execution Prep section of a ticket
- `policy_name` — active policy (e.g., `DEFAULT`, `RISK_OFF`)

> If no comment is provided, the system will attempt a **heuristic match** (same symbol + direction + price within 0.1% tolerance + within 5-minute window of an active ExecutionPrep). Heuristic matches have lower confidence (0.8 vs 1.0) and may be UNMATCHED if ambiguous.

## v2 Changelog

- Added `OnTrade()` handler: fires on every deal and POSTs fill events.
- Added `SyncPositions()`: sends all open position snapshots every 30 seconds.
- Added `InpAccountId` input parameter for multi-account support.
- Increased `WebRequest` timeout to 1000ms for reliability.

---

**Note**: This bridge is strictly for data ingestion. Order execution remains a manual/reviewed process via the Dashboard.
