# Action Items - Next Steps

## 🚀 Immediate Actions (This Week)

### Day 1: Local Testing & Validation

```bash
# 1. Install new dependencies
pip install -r requirements.txt

# 2. Test security modules
python -c "from shared.security import SecretsManager; print(SecretsManager('development').get('POSTGRES_USER'))"

# 3. Run all tests
make test-cov

# 4. Run security scans
bandit -r shared/ services/
safety check

# 5. Pre-commit validation
pre-commit run --all-files
```

**Expected Output**: All tests pass, no security warnings, no lint errors

---

### Day 2: Secrets Setup (AWS/Vault)

#### Option A: AWS Secrets Manager (Recommended for AWS deployments)

```bash
# 1. Create secret
aws secretsmanager create-secret \
  --name trading-system/prod \
  --description "Production secrets for trading system" \
  --secret-string '{
    "POSTGRES_USER": "trading_admin",
    "POSTGRES_PASSWORD": "<generate-strong-password>",
    "POSTGRES_HOST": "db.example.com",
    "API_SECRET_KEY": "<generate-random-key>",
    "JWT_SECRET_KEY": "<generate-random-key>",
    "MT5_API_KEY": "<from-broker>",
    "MT5_MASTER_PASSWORD": "<from-broker>",
    "TELEGRAM_BOT_TOKEN": "<from-telegram>",
    "TELEGRAM_CHAT_ID": "<your-chat-id>"
  }'

# 2. Verify access
aws secretsmanager get-secret-value --secret-id trading-system/prod

# 3. Update docker-compose.prod.yml
export AWS_SECRET_NAME=trading-system/prod
export AWS_REGION=us-east-1
docker-compose -f docker-compose.prod.yml config | grep -i secret
```

#### Option B: HashiCorp Vault (For complex deployments)

```bash
# 1. Authenticate
vault login -method=ldap username=YOUR_USERNAME

# 2. Create secrets
vault kv put secret/trading-system/prod \
  POSTGRES_PASSWORD="<password>" \
  JWT_SECRET_KEY="<key>" \
  ...

# 3. Verify
vault kv get secret/trading-system/prod

# 4. Set environment
export VAULT_ADDR=https://vault.example.com:8200
export VAULT_TOKEN=s.xxxxxxx
```

---

### Day 3: GitHub Actions Setup

```bash
# 1. Generate deployment SSH key
ssh-keygen -t ed25519 -f /tmp/deploy_key -N ""

# 2. Add public key to deployment servers
ssh-copy-id -i /tmp/deploy_key.pub deploy@staging.example.com
ssh-copy-id -i /tmp/deploy_key.pub deploy@prod.example.com

# 3. Add to GitHub Actions secrets (Web UI)
# Settings → Secrets and variables → Actions → New repository secret
#
# STAGING_DEPLOY_KEY: (paste private key content)
# STAGING_HOST: staging.example.com
# PROD_DEPLOY_KEY: (paste private key content)
# PROD_HOST: prod.example.com
# SLACK_WEBHOOK: https://hooks.slack.com/... (optional)

# 4. Verify workflow files
git push origin main  # Triggers CI workflow
```

**Expected Result**: ✅ CI pipeline runs, tests pass, docker image builds

---

### Day 4: Staging Deployment Testing

```bash
# 1. Deploy to staging
git checkout develop
git pull origin develop
docker-compose up -d

# 2. Run integration tests
ENVIRONMENT=staging python -m pytest tests/integration/ -v

# 3. Health check
curl http://localhost:8006/health | jq

# 4. Smoke tests
./scripts/smoke_test.sh

# 5. Monitor logs
docker-compose logs -f orchestration | grep -E "(ERROR|WARNING|Task)"

# 6. Load test (optional)
k6 run tests/load/fundamentals.js
```

**Expected Result**: All endpoints responsive, no error logs, health checks passing

---

### Day 5: Production Deployment

#### Pre-Deployment Checklist

- [ ] CHANGELOG.md updated
- [ ] VERSION file bumped
- [ ] All tests passing locally
- [ ] Security scans clean
- [ ] Database backups verified
- [ ] Rollback plan documented
- [ ] Team notified
- [ ] On-call engineer available

#### Production Deployment Steps

```bash
# 1. Create release branch
git checkout -b release/v1.1.0
echo "1.1.0" > VERSION
git add VERSION CHANGELOG.md
git commit -m "Release v1.1.0"

# 2. Create pull request
git push origin release/v1.1.0
# Create PR, wait for CI to pass

# 3. Merge to main
git checkout main
git pull origin main
git merge --no-ff release/v1.1.0 -m "Merge release v1.1.0"
git push origin main

# 4. Trigger deployment workflow
# Via GitHub UI: Actions → Deployment Pipeline → Run workflow
# Select environment: production

# 5. Monitor deployment
# Watch GitHub Actions logs
# Monitor application logs: docker-compose logs -f
# Check health endpoint: curl https://api.trading.example.com/health

# 6. Verify functionality
curl https://api.trading.example.com/briefings/latest
curl https://api.trading.example.com/metrics
```

**Expected Result**: ✅ Deployment succeeds, health checks pass, no errors

---

### Day 6-7: Validation & Monitoring

```bash
# 1. Enable monitoring alerts
datadog/prometheus monitoring should be set up and alerting configured

# 2. Review logs for errors
docker-compose logs orchestration | grep ERROR

# 3. Monitor background tasks
# Check task status in /health endpoint
watch -n 5 'curl http://api.example.com/health | jq .checks.background_tasks'

# 4. Test failover
# Kill orchestration service, verify automatic restart
docker-compose kill orchestration
sleep 10
docker-compose logs orchestration | grep "startup"

# 5. Document runbook
# Update DEPLOYMENT.md with actual commands used
```

---

## 📋 Phase 3 Tasks (Next 2-3 Weeks)

### Week 1: Input Validation & Logging

#### Task 1: Apply Validators to Models

```python
# File: shared/database/models.py
from pydantic import field_validator
from shared.security.validators import SecurityValidators

class OrderTicket(Base):
    @field_validator('entry_price')
    @classmethod
    def validate_entry(cls, v):
        return SecurityValidators.validate_positive_price(v, "entry_price")

    @field_validator('exit_price')
    @classmethod
    def validate_exit(cls, v):
        return SecurityValidators.validate_price_range(v, "exit_price")
```

#### Task 2: Implement Structured Logging

```python
# File: shared/logic/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ],
)
logger = structlog.get_logger()

# Usage
logger.info("order_executed", order_id=123, price=1.234, quantity=100)
# Output: {"event": "order_executed", "order_id": 123, "price": 1.234, ...}
```

**Estimated Effort**: 1 day
**Files to Change**: 5-10 model/service files

---

### Week 2: Performance Optimization

#### Task 1: Fix N+1 Queries

```python
# Before (N+1 query)
packets = db.query(Packet).all()
for packet in packets:
    print(packet.created_by.username)  # + 1 query per packet

# After (eager loading)
from sqlalchemy.orm import joinedload
packets = db.query(Packet).options(
    joinedload(Packet.created_by)
).all()
```

#### Task 2: Add Pagination

```python
@app.get("/briefings")
def list_briefings(db: Session, skip: int = 0, limit: int = 20):
    return db.query(SessionBriefing).offset(skip).limit(limit).all()
```

#### Task 3: Implement Caching

```python
from shared.providers.cache import get_cache

cache = get_cache()
config = cache.get("guardrails_config")
if not config:
    config = load_config_from_db()
    cache.set("guardrails_config", config, ttl=3600)
```

**Estimated Effort**: 2-3 days
**Files to Change**: 8-12 service files

---

### Week 3: Event-Driven Architecture

#### Task 1: Set Up Message Broker

```bash
# Option 1: RabbitMQ
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  rabbitmq:3-management

# Option 2: Kafka
docker run -d --name kafka \
  -p 9092:9092 \
  confluentinc/cp-kafka:latest
```

#### Task 2: Create Event Publisher

```python
# File: shared/messaging/event_publisher.py
class EventPublisher:
    async def publish(self, event_type: str, data: dict):
        # Publish to message broker instead of DB
        await self.channel.basic_publish(
            exchange='trading_events',
            routing_key=event_type,
            body=json.dumps(data)
        )
```

#### Task 3: Refactor Service Communication

```python
# Instead of: DB → Packet table → Query
# Use: Event → Message Broker → Consumer

# Orchest sends event when ticket created
await event_publisher.publish("ticket.created", ticket.dict())

# Journal listens for event
@event_listener("ticket.created")
async def on_ticket_created(data):
    journal.record_ticket(data)
```

**Estimated Effort**: 3-5 days
**Complexity**: High (architectural change)

---

## 🔍 Monitoring & Observability

### Set Up Monitoring

```bash
# 1. Enable Prometheus metrics
docker run -d --name prometheus \
  -p 9090:9090 \
  -v prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# 2. Set up Grafana dashboards
docker run -d --name grafana \
  -p 3000:3000 \
  grafana/grafana

# 3. Configure alerts
# Edit prometheus.yml to add alert rules
groups:
  - name: trading_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status="500"}[5m]) > 0.05
        annotations:
          summary: "High error rate detected"
```

---

## 📊 Success Metrics

After completing all phases, you should have:

### Security ✅

- [x] No hardcoded secrets anywhere
- [x] JWT authentication on all service endpoints
- [x] Input validation on all user inputs
- [x] Security scanners running on every commit
- [ ] 100% code coverage for security-critical functions
- [ ] Regular penetration testing

### Reliability ✅

- [x] Database transactions proper rollback
- [x] Background tasks with timeout protection
- [x] Graceful shutdown of all services
- [ ] <99.9% uptime SLA
- [ ] <100ms p99 latency
- [ ] <5 second recovery time from failures

### Performance

- [ ] Query time <100ms for all endpoints
- [ ] N+1 queries eliminated
- [ ] Caching layer for config (hit rate >90%)
- [ ] Pagination on all list endpoints
- [ ] Response compression enabled

---

## 🆘 Support & Help

**Questions about implementation?**

- Check `IMPLEMENTATION_GUIDE.md` for detailed docs
- Review `PROGRESS_SUMMARY.md` for completed work
- Check commit history for implementation examples

**Issues during deployment?**

1. Check GitHub Actions logs for CI/CD errors
2. Review Docker logs: `docker-compose logs -f service_name`
3. Test connectivity:

   ```bash
   ping db.example.com
   psql -U postgres -h db.example.com -d trading_journal
   ```

4. Verify secrets:

   ```bash
   aws secretsmanager get-secret-value --secret-id trading-system/prod
   ```

**Performance problems?**

1. Check metrics: `curl http://api.example.com/metrics`
2. Profile queries: Enable query logging in PostgreSQL
3. Review logs for N+1 patterns
4. Run load test: `k6 run tests/load/fundamentals.js`

---

**Ready to start?** Begin with Day 1 local testing above! 🚀
