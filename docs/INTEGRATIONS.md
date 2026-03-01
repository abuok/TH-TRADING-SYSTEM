# System Integrations Guide

This document provides instructions for connecting the TH Trading System to external data sources and alerting services.

## 1. Calendar Integration (High-Impact Events)
- **What it powers**: News-gating in `RiskEngine`. Blocks trades during high-impact economic news.
- **Provider**: Forex Factory (via `ForexFactoryCalendarProvider`).
- **Required Env Vars**:
  - `CALENDAR_PROVIDER=forexfactory`
  - `FOREX_FACTORY_API_KEY=[your_key]`
- **Validation**:
  - Run `python -m infra.cli integrations status`
  - Dashboard indicator: "Calendar: forexfactory"

## 2. Market Proxy Integration (Macro Context)
- **What it powers**: DXY and US10Y correlation analysis in `MarketContext`.
- **Provider**: Twelve Data.
- **Required Env Vars**:
  - `PROXY_PROVIDER=real`
  - `TWELVE_DATA_API_KEY=[your_key]`
- **Validation**:
  - Run `curl -L https://api.twelvedata.com/quote?symbol=DXY&apikey=$TWELVE_DATA_API_KEY`
  - CLI: `python -m infra.cli integrations status` shows `RealProxyProvider: OK`.

## 3. MT5 Quote + Spec Bridge
- **What it powers**: Live price feeds and symbol specifications.
- **Provider**: MT5 Live Bridge (FastAPI service in `services/bridge`).
- **Required Env Vars**:
  - `PRICE_PROVIDER=db` (or `real` for direct bridge)
  - `SPEC_PROVIDER=db`
  - `BRIDGE_SECRET=[shared_secret]`
- **Validation**:
  - Check Redis stream `price_quotes` using `redis-cli XREAD COUNT 1 STREAMS price_quotes 0-0`.

## 4. Telegram Alerting
- **What it powers**: Instant notifications for critical system failures (Kill switch, Risk block).
- **Setup**:
  1. Message `@BotFather` on Telegram to create a bot and get the `TOKEN`.
  2. Message `@userinfobot` to get your `CHAT_ID`.
- **Required Env Vars**:
  - `TELEGRAM_TOKEN=[token]`
  - `TELEGRAM_CHAT_ID=[chat_id]`
- **Validation**:
  - Trigger a test alert via CLI (to be implemented) or manually set a Kill Switch.

## 5. Risk Service Wiring
- **Streams used**: `market_context`, `technical_setups` -> `risk_approvals`.
- **Service**: `services/risk/main.py`.
- **Validation**:
  - CLI: `python -m infra.cli integrations status` should show `Stream 'market_context': OK (risk_group)`.
