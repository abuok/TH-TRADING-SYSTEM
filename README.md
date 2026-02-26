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

3. **Access Dashboard**:
   Open [http://localhost:8005/dashboard](http://localhost:8005/dashboard) in your browser.

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
