# Provider Interface Map

This map outlines the internal interfaces and their available implementations.

| Interface | Implementation | Env Var Setting | Selection Logic |
| :--- | :--- | :--- | :--- |
| CalProvider | Mock | CALENDAR_PROVIDER=mock | **Default.** Demo data. |
| | ForexFactory | CP=forexfactory | Live JSON feed. |
| ProxyProvider | Mock | PROXY_PROVIDER=mock | **Default.** No prod use. |
| | Real | PROXY_PROVIDER=real | 12Data US10Y/DXY. |
| `PriceQuote` | `Mock` | `PRICE_PROVIDER=mock` | **Default.** No prod use. |
| | `DB` | `PRICE_PROVIDER=db` | PostgreSQL history. |
| | `Real` | `PRICE_PROVIDER=real` | (Stub) MT5 connection. |
| `SymbolSpec` | `Mock` | `SPEC_PROVIDER=mock` | **Default.** No prod use. |
| | `DB` | `SPEC_PROVIDER=db` | PostgreSQL static specs. |

## Production Defaults (ENV=prod)

When `ENV=prod` is set, factory functions in `shared/providers/` will raise
a `RuntimeError` if any provider is set to `mock`. This is a "Fail-Closed"
safety mechanism to prevent trading on fake data.
