# Provider Interface Map

This map outlines the internal interfaces and their available implementations.

| Interface | Impl | Env Var | Logic |
| --- | --- | --- | --- |
| Calendar | Mock | `CP=mock` | **Default.** Demo. |
| | FF | `CP=ff` | Live JSON feed. |
| Proxy | Mock | `PP=mock` | **Default.** |
| | Real | `PP=real` | 12Data US10Y. |
| Price | Mock | `PQ=mock` | **Default.** |
| | DB | `PQ=db` | PostgreSQL history. |
| | Real | `PQ=real` | (Stub) MT5. |
| Symbol | Mock | `SS=mock` | **Default.** |
| | DB | `SS=db` | PostgreSQL specs. |

## Production Defaults (ENV=prod)

When `ENV=prod` is set, factory functions in `shared/providers/` will raise
a `RuntimeError` if any provider is set to `mock`. This is a "Fail-Closed"
safety mechanism to prevent trading on fake data.
