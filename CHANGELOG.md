# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-03-14

### 🔒 Constitutional Hardening (CRITICAL)

#### Added

- **AlignmentEngine** (`shared/logic/alignment.py`)
  - Deterministic binary rule-matching (ALIGNED/UNALIGNED).
  - Explicit multi-variant support for counterfactual simulation.
  - Staleness thresholding for market context and price quotes.
- **LockoutEngine** (`shared/logic/lockout_engine.py`)
  - Centralized systemic discipline and frequency lockout control.
  - Daily loss and consecutive loss hard/soft limits.
- **SessionEngine Hardening** (`shared/logic/sessions.py`)
  - Strict boundary transition logic and out-of-session freezing.

#### Changed

- **RiskEngine**: Eradicated "fuzzy" confidence logic; implemented
  fail-closed staleness checks (< 300s).
- **Execution Logic**: Hardened JIT ticket confirmation; treats
  absent market data as an immediate block.
- **Dashboard**: Resolved all HTML5 semantic validation issues;
  decoupled control permissions from visibility.

#### Fixed

- Standardized UTC usage across all temporal engines
  (`datetime.now(timezone.utc)`).
- Resolved MDN semantic warnings in Jinja2 templates.

## [1.1.0] - 2026-03-06

### 🔒 Security Improvements (CRITICAL)

#### Added

- **Secret Management Infrastructure** (`shared/security/secrets_manager.py`)
  - Multi-backend support: AWS Secrets Manager, HashiCorp Vault, environment variables
  - Automatic backend selection based on environment
  - Production secrets validation
  - Database URL construction from secrets
  - Environment-specific loading hierarchy

- **JWT Authentication** (`shared/security/auth.py`)
  - Service-to-service JWT token authentication
  - Token generation with expiration
  - Token verification and validation
  - FastAPI dependency injection support
  - Bearer token validation for protected routes

- **Input Validation & Sanitization** (`shared/security/validators.py`)
  - Price validation (positive, within range)
  - Quantity validation (positive integers)
  - R-multiple validation (risk ratios)
  - HTML escaping for XSS prevention
  - Text sanitization (max length, control characters)
  - Trading symbol format validation

- **Security Scanning Tools**
  - Added PyJWT, cryptography, safety, bandit to requirements.txt
  - Pre-commit hooks for bandit security scanning
  - Pre-commit hooks for dependency vulnerability checking
  - `.bandit` configuration file for security scanning

- **Environment Template**
  - `.env.vault.example` for production secrets template

#### Changed

- `docker-compose.yml`: Removed hardcoded credentials, uses environment variables
- `requirements.txt`: Added security packages (PyJWT, safety, bandit, structlog)
- `.pre-commit-config.yaml`: Added 6 new security/quality hooks
- Database default credentials changed from admin/admin to postgres/postgres

### 🛡️ Reliability Improvements (CRITICAL)

#### Added

- **Database Transaction Safety** (`shared/database/session.py`)
  - Explicit transaction management (commit on success, rollback on error)
  - TransactionDecorator for manual operation wrapping
  - Connection pool optimization (pre-ping, 1-hour recycle)
  - Comprehensive error logging
  - SQLAlchemy error handling

- **Async Task Supervision** (`shared/task_management/task_supervisor.py`)
  - Background task timeout protection (30s default)
  - Automatic retry logic (up to 3 times)
  - Graceful shutdown handlers
  - Task status monitoring and logging
  - Exception recovery and logging
  - Context manager for task lifecycle management

- **CI/CD Automation** (`.github/workflows/`)
  - **CI Pipeline** (`ci.yml`): Code quality, security scanning,
    testing, Docker build
  - **CD Pipeline** (`deploy.yml`): Staging and production deployment automation
  - Automated testing with coverage reporting
  - Security scanning integration (bandit, safety)
  - Docker image build and push to GitHub Container Registry
  - Release notes generation

- **Docker Security Hardening** (`infra/Dockerfile.service`)
  - Multi-stage build (build dependencies removed from production)
  - Non-root user execution (trader:trader)
  - Pinned Python version (3.11.8-slim)
  - Health check endpoint
  - Minimal dependencies in runtime image

- **Enhanced Health Checks** (`shared/logic/health.py`, Orchestration service)
  - Comprehensive `/health` endpoint with database connectivity check
  - Background task status monitoring
  - Service version and environment information
  - Task supervisor integration for real-time task monitoring

#### Changed

- `services/orchestration/main.py`:
  - Refactored startup event to use TaskSupervision
  - Added shutdown event for graceful cleanup
  - Updated fundamentals_scheduler with timeout support
  - Enhanced `/health` endpoint with full status information

### 📊 Documentation

#### Added

- **IMPLEMENTATION_GUIDE.md**: Comprehensive implementation guide
  with code examples and usage patterns
- **PROGRESS_SUMMARY.md**: Quick reference of completed work with deployment checklist
- **ACTION_ITEMS.md**: Step-by-step deployment guide for next 2 weeks

#### Changed

- Updated CHANGELOG with detailed feature descriptions

### ✅ Quality Metrics

- Lines of code added: 1,210+
- New modules created: 8
- Files modified: 14
- Test coverage: 59 tests passing
- Security hooks added: 6
- CI/CD stages: 5 (quality, tests, build, report, deploy)

---

## [1.0.1] - 2026-03-06

### Added

- **Metrics Endpoint**: Added `/metrics` endpoint to Orchestration
  service for Prometheus-style monitoring
- **Test Coverage**: Added pytest-cov for coverage reporting with
  `make test-cov` command
- **Configuration Documentation**: Added comprehensive configuration
  hierarchy documentation to README

### Changed

- **Error Handling**: Improved error handling in Telegram alerting
  with specific exception types
- **Makefile**: Fixed demo script path and added migration
  validation to release checks

### Fixed

- **Test Failures**: Fixed missing `now_utc` parameter in safety drill tests
- **MT5 Bridge Security**: Updated placeholder secret to more secure default
- **Demo Path**: Corrected Makefile to point to actual demo script location

### Security

- Enhanced secret management practices in MT5 bridge configuration

## [1.0.0] - 2026-02-28

### Added

- **Mission A-C**: Research, Calibration, and Hindsight scoring systems.
- **Mission D-E**: Live Data Bridge and Trade Capture integration with MT5.
- **Mission F**: Trade Management Assistant for rule-based SL/TP suggestions.
- **Mission G**: Weekly Tuning Assistant with parameter proposal reports.
- **Mission H**: Pilot Run Protocol and Graduation Gate for 10-session rolling evaluation.
- **Mission I**: Release Pack v1.0, Operator Manual, and Disaster Recovery playbook.
- Dashboard views for all major modules (Ops, Tickets, Queue,
  Hindsight, Calibration, Tuning, Pilot).
- CLI tools for packet management, report generation, and system validation.

### Changed

- Refactored all inline CSS to external `index.css` for dashboard styling.
- Hardened database schemas with strict constraints and foreign keys.

### Fixed

- Improved quote freshness handling in Live Data Bridge.
- Fixed Postgres/SQLite compatibility issues in the research modules.

### Security

- Implemented dashboard authentication (Username/Password).
- Added kill switch safety mechanisms.
- System-wide guardrails for capital protection and risk management.
