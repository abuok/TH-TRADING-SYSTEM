# Integration Guide

This document outlines the steps required to transition the TH Trading System from "Mock" data to real-world production feeds.

## 1. Economic Calendar (Safety Gate)
The system uses the economic calendar to avoid trading ±15 minutes around high-impact news.

### Setup Steps
1. **Provider**: ForexFactory (RSS Feed)
2. **Configuration**: Set `CALENDAR_PROVIDER=forexfactory` in `.env.prod`.
3. **Verification**: 
   - Run `python -m services.ingestion.main` and check `/health`.
   - Ensure `CalendarProvider` shows `ForexFactoryCalendarProvider`.
   - Check `market_context` events in the logs/dashboard.

## 2. Market Proxies (Fundamental Bias)
Provides correlation data for DXY (Dollar Index), US10Y (Yields), and SPX.

### Setup Steps
1. **Provider Options**: 
   - **Twelve Data** (Recommended): Reliable, free tier available.
   - **AlphaVantage**: Good fallback.
2. **Implementation**: `shared/providers/proxy.py` requires `RealProxyProvider` implementation.
3. **Configuration**: 
   - Set `PROXY_PROVIDER=real`.
   - Add `TWELVE_DATA_API_KEY=your_key_here`.

## 3. Live Price Quotes & Symbol Specs
Provided by the MT5 Bridge.

### Setup Steps
1. **MT5 Connector**: Ensure the `phx-bridge-mt5` (Expert Advisor) is running on your terminal.
2. **Endpoints**: 
   - Quotes: `POST /bridge/quote`
   - Specs: `POST /bridge/spec`
3. **Configuration**: 
   - Set `PRICE_PROVIDER=db`.
   - Set `SPEC_PROVIDER=db`.
4. **Validation**: 
   - `curl http://localhost:8001/health` (Bridge status).
   - Check "Live Data" tab on the dashboard.

## 4. Trade Capture & History
Synchronizes executed trades from MT5 to the local DB.

### Setup Steps
1. **Comment Format**: Trades MUST have a comment like `TKT-123` matching the local `OrderTicket` ID.
2. **History Sync**: Ensure the Bridge `post_trade_capture` endpoint is reachable.
3. **Configuration**: None (Automatic if Bridge is active).

## 5. Environment Variables Summary (.env.prod)
| Key | Example | Description |
| :--- | :--- | :--- |
| `CALENDAR_PROVIDER` | `forexfactory` | `mock` or `forexfactory` |
| `PROXY_PROVIDER` | `real` | Must implement adapter first |
| `PRICE_PROVIDER` | `db` | `mock` or `db` |
| `SPEC_PROVIDER` | `db` | `mock` or `db` |
| `DASHBOARD_PASSWORD`| `********` | Production-grade password |

## Debugging & Failure Modes
- **Stale Quotes**: If `LiveQuote` isn't updated for >30s, the system enters "FAIL CLOSED" mode for new tickets.
- **Ingestion Failure**: If RSS fails, `CalendarProvider` returns `[]`. 
  - **WARNING**: This defaults to "Safe" (No news). To harden, change `fetch_events` to raise on error if safety-critical.
