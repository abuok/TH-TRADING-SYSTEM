# PHX Live Data Bridge - MT5 EA Template

This directory contains the `LiveBridgeEA.mq5` source code to feed real-time quotes and symbol specifications from MetaTrader 5 into the PHX Trading System.

## Features
- **Data-only**: No order execution logic. Only sends Bid/Ask and Symbol Specs.
- **Configurable Sync**: Adjust sync interval to balance latency vs. bandwidth.
- **Secure**: Uses a shared secret header to authorize requests to the Bridge service.

## Installation
1. Open MetaTrader 5.
2. Go to `File` -> `Open Data Folder`.
3. Navigate to `MQL5` -> `Experts`.
4. Create a folder named `PHX` and paste `LiveBridgeEA.mq5` into it.
5. In MT5, open the `Navigator` (Ctrl+N), right-click `Experts`, and select `Refresh`.
6. Attach the EA to any chart (e.g., XAUUSD).

## Configuration
When attaching the EA, set the following parameters:
- **Server URL**: The URL where your `services/bridge` is running (e.g., `http://your-vps-ip:8005`).
- **Bridge Secret**: Must match the `BRIDGE_SECRET` environment variable in your `.env` file.
- **Sync Interval**: Number of seconds between quote updates (Default: 5).

## Important: WebRequest Permissions
For the EA to communicate with the Bridge service, you MUST allow the server URL in MT5:
1. Go to `Tools` -> `Options` -> `Expert Advisors`.
2. Check `Allow WebRequest for listed URL`.
3. Add your Bridge Server URL (e.g., `http://localhost:8005`).

---
**Note**: This bridge is for data ingestion only. Order execution remains a manual/reviewed process via the PHX Dashboard.
