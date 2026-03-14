# Docker Quick Reference

## Files Generated

- **Dockerfile** - Optimized development image with hot reload support
- **Dockerfile.prod** - Security-hardened production image  
- **docker-compose.yml** - Development stack with hot reload (watch mode)
- **docker-compose.prod.yml** - Production stack with resource limits & logging
- **.dockerignore** - Optimizes build context
- **DOCKER_BEST_PRACTICES.md** - Detailed documentation

## Quick Start

### Development (with hot reload)

```bash
# Start all services
docker compose up

# Start with automatic file watching (recommended for active development)
docker compose watch

# View logs
docker compose logs -f dashboard

# Stop all services
docker compose down

# Clean everything (volumes too)
docker compose down -v
```

### Production Deployment

```bash
# Build and start production stack
docker compose -f docker-compose.prod.yml up -d

# Check service status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f dashboard

# Graceful shutdown
docker compose -f docker-compose.prod.yml down

# Hard reset (removes volumes)
docker compose -f docker-compose.prod.yml down -v
```

## Common Commands

```bash
# Build images only (no containers)
docker compose build

# Run one-off commands
docker compose run --rm ingestion pytest
docker compose run --rm technical python -m pytest tests/

# Scale a service (dev only)
docker compose up -d --scale risk=3

# Execute commands in running container
docker compose exec dashboard bash
docker compose exec postgres psql -U postgres -d trading_journal

# Check resource usage
docker stats

# View real-time logs with timestamps
docker compose logs -f --timestamps

# Follow specific service
docker compose logs -f orchestration

# Last 50 lines
docker compose logs --tail=50
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose logs ingestion

# Inspect container details
docker inspect <container_id>

# Check service health
docker compose ps
```

### Database connection issues
```bash
# Test Postgres connection
docker compose exec postgres pg_isready -U postgres

# Test Redis connection
docker compose exec redis redis-cli ping
```

### Port conflicts
```bash
# Find what's using a port (Linux/Mac)
lsof -i :8001

# Change port in docker-compose.yml
# services:
#   ingestion:
#     ports:
#       - "8001:8000"  # Change left number
```

### Out of disk space
```bash
# Check Docker disk usage
docker system df

# Clean up unused images, containers, volumes
docker system prune -a --volumes
```

### Rebuild with no cache
```bash
docker compose build --no-cache
docker compose up
```

## Architecture

```
┌─────────────────────────────────────────────┐
│         Docker Compose Network              │
│       (trading-network / trading-internal)  │
└─────────────────────────────────────────────┘
         ↑      ↑      ↑      ↑      ↑
    ┌────┴──────┴──────┴──────┴──────┴────┐
    │                                      │
    │   6 FastAPI Microservices (port 8001-8006)
    │   - Ingestion (8001)
    │   - Technical (8002)
    │   - Risk (8003)
    │   - Journal (8004)
    │   - Dashboard (8005) ← Exposed publicly
    │   - Orchestration (8006)
    │                                      │
    └────────────────────────────────────┘
              ↑                    ↑
        ┌─────┴────┐        ┌─────┴─────┐
        │           │        │           │
    ┌───┴──┐    ┌──┴───┐ ┌──┴───┐  ┌──┴───┐
    │      │    │      │ │      │  │      │
    │ DB   │    │Cache │ │ Net  │  │ Logs │
    │(5432)│    │(6379)│ │Bridge│  │JSON  │
    │      │    │      │ │      │  │      │
    └──────┘    └──────┘ └──────┘  └──────┘
```

## Performance Tips

1. **Use named volumes** for databases (persists data across restarts)
2. **Enable BuildKit** for faster builds: `export DOCKER_BUILDKIT=1`
3. **Use .dockerignore** to reduce context size
4. **Layer caching**: Install requirements before copying code
5. **Health checks**: Enable service dependencies with proper conditions
6. **Resource limits**: Set in production to prevent runaway containers

## Security Notes

- Non-root user (`trader`) runs all services
- Production image excludes build tools
- Network isolation with bridge networks
- Read-only volumes where applicable
- Environment variables for secrets (never hardcode)
- HTTPS ready with ca-certificates

## Files to Create/Update

Create these before running production:

**.env.prod** - Production environment variables
```
POSTGRES_USER=secure_username
POSTGRES_PASSWORD=strong_password_here
REDIS_PASSWORD=another_strong_password
ENVIRONMENT=production
DEBUG=False
```

**.env** - Development environment (already in .gitignore)
```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=trading_journal
```

## Monitoring & Observability

```bash
# Real-time resource usage
docker stats

# View system events
docker events

# Inspect network connections
docker network inspect trading-network

# Check volume mounts
docker inspect --format='{{json .Mounts}}' <container_id> | jq
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Build Production Image
  run: docker compose -f docker-compose.prod.yml build

- name: Push to Registry
  run: docker push your-registry/trading-system:prod
```

### Push to Docker Hub/Registry
```bash
# Tag image
docker tag trading-system:dev your-username/trading-system:latest

# Push
docker push your-username/trading-system:latest
```
