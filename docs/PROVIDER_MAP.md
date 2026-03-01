# Provider Interface Map

This map defines the abstract interfaces used for external integrations and their current implementation status.

## 1. CalendarProvider
- **Path**: `shared/providers/calendar.py`
- **Interface**: `fetch_events()`, `get_no_trade_windows()`
- **Implementations**:
  - `MockCalendarProvider`: Default. Returns empty event list.
  - `ForexFactoryCalendarProvider`: Fetches high-impact news from RSS.
- **Factory**: `get_calendar_provider()` via `CALENDAR_PROVIDER`.

## 2. ProxyProvider
- **Path**: `shared/providers/proxy.py`
- **Interface**: `get_snapshots()`
- **Implementations**:
  - `MockProxyProvider`: Default. Returns static DXY/US10Y/SPX values.
  - `RealProxyProvider`: **Stub**. Raises `NotImplementedError`.
- **Factory**: `get_proxy_provider()` via `PROXY_PROVIDER`.

## 3. PriceQuoteProvider
- **Path**: `shared/providers/price_quote.py`
- **Interface**: `get_quote(symbol)`
- **Implementations**:
  - `MockPriceQuoteProvider`: Default. Matches any entry price.
  - `DBPriceQuoteProvider`: Reads from `LiveQuote` table (fed by Bridge).
  - `RealPriceQuoteProvider`: **Stub**. Raises `NotImplementedError`.
- **Factory**: `get_price_quote_provider()` via `PRICE_PROVIDER`.

## 4. SymbolSpecProvider
- **Path**: `shared/providers/symbol_spec.py`
- **Interface**: `get_spec(symbol)`
- **Implementations**:
  - `MockSymbolSpecProvider`: Default. Hardcoded XAUUSD/EURUSD/GBPJPY.
  - `DBSymbolSpecProvider`: Reads from `SymbolSpec` table (fed by Bridge).
- **Factory**: `get_symbol_spec_provider()` via `SPEC_PROVIDER`.

---

## How to Switch Providers
To switch from Mock to Real implementations, update your `.env` file:
```bash
# Example for VPS Live Execution
CALENDAR_PROVIDER=forexfactory
PRICE_PROVIDER=db
SPEC_PROVIDER=db
PROXY_PROVIDER=mock # Keep mock until TwelveData adapter is written
```
 Providers are instantiated at service startup (e.g., in `IngestionService` or `ExecutionPrep`). Changing env vars requires a service restart.
