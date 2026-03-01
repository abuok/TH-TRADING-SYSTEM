# Provider Interface Map

This map outlines the internal interfaces and their available implementations.

| Interface | Implementation | Env Var Setting | Selection Logic |
|-----------|----------------|-----------------|-----------------|
| `CalendarProvider` | `MockCalendarProvider` | `CALENDAR_PROVIDER=mock` | **Default.** Deterministic data. Forbidden in `ENV=prod`. |
| | `ForexFactoryCalendarProvider` | `CALENDAR_PROVIDER=forexfactory` | Fetches JSON feed from Forex Factory. |
| `ProxyProvider` | `MockProxyProvider` | `PROXY_PROVIDER=mock` | **Default.** Forbidden in `ENV=prod`. |
| | `RealProxyProvider` | `PROXY_PROVIDER=real` | Uses Twelve Data API for US10Y/DXY. |
| `PriceQuoteProvider` | `MockPriceQuoteProvider` | `PRICE_PROVIDER=mock` | **Default.** Forbidden in `ENV=prod`. |
| | `DBPriceQuoteProvider` | `PRICE_PROVIDER=db` | Reads latest prices from PostgreSQL. |
| | `RealPriceQuoteProvider` | `PRICE_PROVIDER=real` | (Stub) Direct MT5 bridge connection. |
| `SymbolSpecProvider` | `MockSymbolSpecProvider` | `SPEC_PROVIDER=mock` | **Default.** Forbidden in `ENV=prod`. |
| | `DBSymbolSpecProvider` | `SPEC_PROVIDER=db` | Reads static specs from PostgreSQL. |

## Production Defaults (ENV=prod)
When `ENV=prod` is set, factory functions in `shared/providers/` will raise a `RuntimeError` if any provider is set to `mock`. This is a "Fail-Closed" safety mechanism to prevent trading on fake data.
