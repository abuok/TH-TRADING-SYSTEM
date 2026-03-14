# System Integrations Guide

This document describes how to configure and verify the external integrations
for the TH Trading System.

## 1. Calendar Integration (High-Impact Events)

- **What it powers**: News-gating in `AlignmentEngine` (evaluated at JIT).
  Blocks trades during high-impact economic news.
- **Provider**: Forex Factory (via `ForexFactoryCalendarProvider`).
- **Required Env Vars**:
  - `CALENDAR_PROVIDER=forexfactory`
  - `FOREX_FACTORY_API_KEY=[your_key]`
- **Validation**:
  - Run `python -m infra.cli infra status`
  - Dashboard indicator: "Calendar: forexfactory"

## 2. Proxy Integration (Macro Data)

- **What it powers**: US10Y and DXY trend alignment for fundamental bias.
- **Providers**: `live` (via API) or `mock` (for testing).
- **Required Env Vars**:
  - `PROXY_PROVIDER=real`
  - `PROXY_API_KEY=[your_key]`

## 3. MT5 Bridge (Market Data & Fills)

- **What it powers**: Real-time quotes and automated trade capture.
- **Protocol**: HTTP/HTTPS POST from MT5 to `services/bridge`.
- **Validation**:
  - Check the **Bridge** tab on the Dashboard for active connections.
  - Verify "Quote Freshness" (should be < 30s).
