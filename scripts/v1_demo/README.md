# V1 Demo — Prototype Scripts

These files are the original V1 proof-of-concept simulation for the TH Trading System.
They are **not wired into any production service** and exist only for historical reference.

| File | Purpose |
|---|---|
| `main.py` | Entry point, loops through signal generation |
| `risk_engine.py` | Simple class-based risk checks (in-memory, non-persistent) |
| `signal_generator.py` | Random-direction signal generator (simulation only) |
| `signal_scorer.py` | Confidence scorer |
| `session_manager.py` | Basic session time checker |
| `journal_service.py` | Flat-file JSON journaling |
| `replay_engine.py` | Historical signal replay from JSON |
| `core_models.py` | V1 dataclasses |

> ⚠️  Do NOT import from these files in production code. All production logic lives under `services/` and `shared/`.
