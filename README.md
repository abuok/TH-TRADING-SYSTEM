# Trading System V1 (Monorepo)

A sophisticated multi-agent trading system with deterministic risk engine, journaling, and session management.

## Quickstart: Demo

To run the full end-to-end demo locally:

1. **Install Dependencies**:

   ```bash
   make install
   ```

2. **Run Demo**:

   ```bash
   make demo
   ```

   *This will start the services via Docker, wait for initialization, and run the E2E demo script.*

### 5. Operator Dashboard Monitoring

You can monitor the system in real-time via the Operator Dashboard:

1. Open [http://localhost:8005/dashboard](http://localhost:8005/dashboard).
2. **Overview**: View health status of all 5 microservices, active kill switches, and recent activity.
3. **Tickets Tab**: View human-reviewable trade plans.
   - Use the "Copy MT5" or "Copy cTrader" buttons to get platform-specific notes.
   - Plans blocked by risk are highlighted in red with explicit reasons.

## Pre-commit / Code Quality

[ruff](https://docs.astral.sh/ruff/) is used for both linting and formatting via pre-commit hooks.

**One-time setup** (after cloning):

```bash
pip install pre-commit
pre-commit install
```

**Run on all files manually**:

```bash
pre-commit run --all-files
# or via Make:
make precommit-run
```

The hooks run automatically on every `git commit` and will auto-fix safe issues; re-stage any changes and commit again.

## Project Structure

- `services/`: Specialized microservices (Ingestion, Technical, Risk, Journal, Orchestration).
- `shared/`: Logic, data types, and database utilities shared across services.
- `infra/`: Infrastructure scripts and CLI tools.
- `docs/`: Detailed guides and architecture documentation.

## Running Tests

```bash
make test
```

For more detailed information on the E2E flow, see [docs/END_TO_END_DEMO.md](docs/END_TO_END_DEMO.md).

## Pre-commit (ruff)

Install and enable pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

Run hooks across all files:

```bash
pre-commit run --all-files
```
