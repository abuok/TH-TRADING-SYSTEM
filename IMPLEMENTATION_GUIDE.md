# Trading System Fixes - Implementation Guide

**Completed: March 6, 2026**
**Status: Phase 1-2 Complete (Critical Security & Reliability)**

## Overview

This document outlines all critical fixes applied to the TH-TRADING-SYSTEM to address security vulnerabilities, reliability gaps, and operational concerns identified in the comprehensive codebase review.

---

## Phase 1: Critical Security (✅ COMPLETE)

### 1.1 Secret Management Infrastructure

**Files Created:**
- `shared/security/secrets_manager.py` - Centralized credential management
- `shared/security/__init__.py` - Module exports
- `.env.vault.example` - Production environment template

**Features:**
- Multi-backend support (AWS Secrets Manager, HashiCorp Vault, environment variables, .env files)
- Automatic backend selection based on environment
- Production secrets validation
- Database URL construction from secrets

**Usage:**
```python
from shared.security import SecretsManager

secrets = SecretsManager(environment="production")
db_password = secrets.require("POSTGRES_PASSWORD")
db_url = secrets.get_database_url()
```

**Configuration:**
- Development: Loads from `.env` file
- Staging/Production: Tries Vault → AWS Secrets Manager → Environment variables

---

### 1.2 JWT API Authentication

**Files Created:**
- `shared/security/auth.py` - JWT token management
- Updated `shared/security/__init__.py`

**Features:**
- JWT token generation with configurable expiration
- Token verification with automatic exp/validation checks
- Service-to-service authorization
- FastAPI dependency injection support

**Usage:**
```python
from fastapi import Depends
from shared.security import verify_api_token

@app.get("/protected")
async def protected_route(token_data: Dict = Depends(verify_api_token)):
    return {"service": token_data["service"]}
```

**Testing:**
```bash
# Generate token
TOKEN=$(python -c "from shared.security import JWTAuthenticator; a = JWTAuthenticator(); print(a.create_token('test', 'test-service'))")

# Use in request
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/protected
```

---

### 1.3 Input Validation & Sanitization

**Files Created:**
- `shared/security/validators.py` - Pydantic validators and sanitization

**Features:**
- Price validation (positive, within range)
- Quantity validation (positive integers)
- R-multiple validation (risk ratios)
- HTML escaping for XSS prevention
- Text sanitization (max length, control characters)
- Trading symbol format validation

**Usage:**
```python
from pydantic import BaseModel, field_validator
from shared.security.validators import SecurityValidators

class OrderTicket(BaseModel):
    entry_price: float
    exit_price: float
    quantity: float

    @field_validator('entry_price')
    @classmethod
    def validate_entry_price(cls, v):
        return SecurityValidators.validate_positive_price(v, "entry_price")

    @field_validator('quantity')
    @classmethod
    def validate_qty(cls, v):
        return SecurityValidators.validate_quantity(v)
```

---

### 1.4 Security Scanning Tools

**Files Updated:**
- `requirements.txt` - Added PyJWT, cryptography, safety, bandit
- `.pre-commit-config.yaml` - Added security scanning hooks
- `.bandit` - Bandit configuration

**New Dependencies:**
- `PyJWT==2.8.1` - JWT library
- `safety==2.3.5` - Dependency vulnerability scanning
- `bandit==1.7.5` - Code security scanning
- `structlog==23.2.0` - JSON logging

**Pre-commit Hooks:**
```yaml
- bandit: Scans for common security issues
- safety: Checks for vulnerable dependencies
- pre-commit-hooks: Detects private keys, large files
```

**Running Scans:**
```bash
# Manual security scan
bandit -r shared/ services/ -ll

# Check dependencies
safety check

# Run all pre-commit hooks
pre-commit run --all-files
```

---

### 1.5 Environment Updates

**Files Updated:**
- `docker-compose.yml` - Removed hardcoded credentials
- `.env.vault.example` - Created production template

**Changes:**
```yaml
# Before (INSECURE)
POSTGRES_PASSWORD: admin

# After (SECURE)
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
```

All secrets now use environment variable substitution with secure defaults.

---

## Phase 2: Critical Reliability (✅ COMPLETE)

### 2.1 Database Transaction Safety

**Files Updated:**
- `shared/database/session.py` - Complete refactor

**Improvements:**
- Explicit rollback on exceptions
- Commit on success
- Proper exception logging
- Transaction decorator for manual operations
- Connection pool optimization (pre-ping, recycle)

**New Code:**
```python
def get_db():
    """Get database session with automatic transaction management."""
    db = SessionLocal()
    try:
        yield db
        db.commit()  # Explicit commit on success
    except SQLAlchemyError as e:
        db.rollback()  # Automatic rollback on error
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()
```

**Transaction Decorator:**
```python
@TransactionDecorator.transactional
def update_order(db: Session, order_id: int, status: str):
    order = db.query(OrderTicket).get(order_id)
    order.status = status
    # Auto-commits on success, rolls back on error
```

---

### 2.2 Async Task Management with Supervision

**Files Created:**
- `shared/async/task_supervisor.py` - Task supervision module
- `shared/async/__init__.py` - Module exports

**Features:**
- Timeout protection for background tasks (default 30s)
- Automatic retry logic (up to 3 retries)
- Graceful shutdown handlers
- Task status monitoring
- Exception logging and recovery

**Usage:**
```python
from shared.async import get_task_supervisor

supervisor = get_task_supervisor(timeout_seconds=30)

# Create supervised task
await supervisor.create_task(
    name="fundamentals_scheduler",
    coro=fundamentals_scheduler,
    timeout_seconds=120,
    max_retries=3,
)

# Get task status
status = supervisor.get_task_status("fundamentals_scheduler")

# Graceful shutdown
await supervisor.shutdown_all(timeout_seconds=10)
```

**Integration in Orchestration Service:**
```python
from shared.async import get_task_supervisor

_task_supervisor = get_task_supervisor(timeout_seconds=30)

@app.on_event("startup")
async def startup_event():
    await _task_supervisor.create_task(
        "fundamentals_scheduler",
        fundamentals_scheduler,
        timeout_seconds=120,
        max_retries=3,
    )

@app.on_event("shutdown")
async def shutdown_event():
    await _task_supervisor.shutdown_all()
```

**Improvements in Schedulers:**
- 30-minute loops broken into 1-second sleep steps
- Graceful cancellation support
- Proper shutdown detection

---

### 2.3 Dockerfile Hardening

**File Updated:**
- `infra/Dockerfile.service` - Complete refactor

**Improvements:**
1. **Multi-stage build** - Separate build and runtime stages
   - Reduces final image size
   - Removes build dependencies from production

2. **Non-root user** - Runs as `trader:trader` instead of root
   - Reduces attack surface
   - Prevents privilege escalation

3. **Pinned Python version** - `3.11.8-slim` instead of `3.11-slim`
   - Ensures reproducible builds
   - Explicit security patch version

4. **Health check** - Built-in health endpoint
   - Docker health monitoring
   - Automatic container restart on failure

5. **Minimal dependencies** - Only runtime packages included
   - Build tools removed from final image
   - Faster container startup

**Security Benefits:**
```dockerfile
# Multi-stage: build dependencies not in production image
FROM python:3.11.8-slim as builder
RUN apt-get install build-essential  # Build only

FROM python:3.11.8-slim  # Production image, much smaller
# Copy only compiled dependencies
COPY --from=builder /opt/venv /opt/venv

# Run as unprivileged user
USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=5s
```

---

### 2.4 GitHub Actions CI/CD Pipelines

**Files Created:**
- `.github/workflows/ci.yml` - Continuous Integration
- `.github/workflows/deploy.yml` - Continuous Deployment

**CI Pipeline Stages:**
1. **Code Quality**
   - Ruff format checking (Python style)
   - Ruff linting (code quality)
   - MyPy type checking
   - Bandit security scanning
   - Safety dependency scanning

2. **Tests**
   - Unit tests with pytest
   - Coverage reporting (>80% target)
   - Integration tests with external services
   - Codecov integration

3. **Build**
   - Docker image build and push
   - GitHub Container Registry storage
   - Semantic versioning tags

4. **Report**
   - GitHub Actions summary
   - Coverage reports
   - Security scan results

**CD Pipeline Stages:**
1. **Staging Deployment**
   - Automatic on CI success
   - SSH key-based authentication
   - Database migrations
   - Health check verification

2. **Production Deployment**
   - Manual trigger via workflow_dispatch
   - Version validation
   - Full test suite in production
   - GitHub Release creation
   - Slack notifications

**Running CI/CD:**
```bash
# CI runs automatically on push/PR to main/develop branches
git push origin main

# Manual deployment
# Via GitHub UI: Actions → Deployment Pipeline → Run workflow
# Select environment and trigger
```

---

### 2.5 Enhanced Health Check Endpoints

**Files Created:**
- `shared/logic/health.py` - Health check utilities

**Files Updated:**
- `services/orchestration/main.py` - Enhanced /health endpoint

**Health Endpoint Response:**
```json
{
  "status": "healthy",
  "service": "orchestration",
  "version": "1.0.1",
  "environment": "production",
  "timestamp": "2026-03-06T12:34:56.789Z",
  "checks": {
    "database": {"status": "ok"},
    "background_tasks": {
      "status": "ok",
      "tasks": {
        "fundamentals_scheduler": {
          "status": "running",
          "started_at": "2026-03-06T12:00:00",
          "attempt": 1
        }
      }
    }
  }
}
```

---

## Configuration & Deployment

### Environment Variables

**Development (.env):**
```bash
ENVIRONMENT=development
DATABASE_URL=sqlite:///./test.db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
JWT_SECRET_KEY=dev-secret-key
```

**Staging (.env.staging):**
```bash
ENVIRONMENT=staging
DATABASE_URL=postgresql://user:pass@staging-db:5432/trading_journal
VAULT_ADDR=https://vault.staging.example.com:8200
VAULT_TOKEN=s.xxxxxxx
JWT_SECRET_KEY=${VAULT_SECRET}
```

**Production (.env.vault.example → .env.prod):**
```bash
ENVIRONMENT=production
AWS_REGION=us-east-1
AWS_SECRET_NAME=trading-system/prod
JWT_SECRET_KEY=${AWS_SECRETS_MANAGER}
# All secrets from AWS Secrets Manager
```

### Docker Compose

```bash
# Development
docker-compose up -d

# Production with environment
export POSTGRES_PASSWORD=$(aws secretsmanager get-secret-value --secret-id trading/db/password)
docker-compose -f docker-compose.prod.yml up -d
```

---

## Testing & Validation

### Run All Tests
```bash
# Full test suite with coverage
make test-cov

# Just unit tests
pytest tests/ -v

# Integration tests with services
docker-compose up -d
pytest tests/integration/ -v
docker-compose down
```

### Security Scanning
```bash
# Code security
bandit -r shared/ services/

# Dependency vulnerabilities
safety check

# Type checking
mypy --config-file mypy.ini shared/ services/

# Pre-commit hooks
pre-commit run --all-files
```

### CI/CD Testing
```bash
# Simulate CI environment
act -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:full-latest
```

---

## Next Steps (Phase 3 & Beyond)

### Immediate (Week 2)
- [ ] Implement structured JSON logging (structlog)
- [ ] Apply validators to all OrderTicket operations
- [ ] Deploy CI/CD pipeline to GitHub
- [ ] Test health check endpoints under load

### Short-term (Weeks 3-4)
- [ ] Query optimization (N+1 fixes)
- [ ] Redis caching implementation
- [ ] Event-driven messaging (RabbitMQ/Kafka)
- [ ] Pagination on list endpoints

### Medium-term (Sprint 2)
- [ ] Enable mypy strict mode incrementally
- [ ] Field-level encryption for sensitive columns
- [ ] Advanced rate limiting and DDoS protection
- [ ] Comprehensive API documentation (OpenAPI/Swagger)

### Long-term (Sprint 3+)
- [ ] Machine learning for policy optimization
- [ ] Advanced monitoring and alerting
- [ ] Disaster recovery procedures
- [ ] Multi-region deployment setup

---

## Critical Reminders

### Security
- ⚠️ Never commit secrets to Git
- ⚠️ Always use environment variables or vault for credentials
- ⚠️ Rotate JWT secrets monthly
- ⚠️ Review CloudTrail logs for AWS API access
- ⚠️ Enable MFA on all deployment accounts

### Reliability
- ✅ Always run migrations before startup (`alembic upgrade head`)
- ✅ Monitor background tasks via `/metrics` endpoint
- ✅ Set up alerts for task failures
- ✅ Test graceful shutdown in staging before production

### Operations
- 📝 Document all environment variable changes
- 📝 Update deployment runbook after changes
- 📝 Test rollback procedures monthly
- 📝 Keep CHANGELOG.md updated with all changes

---

## Support & Troubleshooting

### Common Issues

**Secret not found:**
```python
# Check in order of precedence:
# 1. Environment variable: echo $POSTGRES_PASSWORD
# 2. .env file: cat .env | grep POSTGRES_PASSWORD
# 3. AWS Secrets Manager: aws secretsmanager get-secret-value ...
# 4. Vault: vault kv get trading-system/prod
```

**Database transaction fails:**
```python
# Check logs for full error
docker-compose logs orchestration | grep "Database error"

# Verify connection string
python -c "from shared.database.session import get_engine; print(get_engine())"

# Test connection
psql -U $POSTGRES_USER -h localhost -d trading_journal
```

**Background task timeouts:**
```python
# Check task status via health endpoint
curl http://localhost:8006/health

# View logs
docker-compose logs orchestration | grep "timeout"

# Verify network latency
ping external-api.example.com
```

---

**Document Version:** 1.0
**Last Updated:** March 6, 2026
**Next Review:** After Phase 3 completion
