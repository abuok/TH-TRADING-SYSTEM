# PHX VPS Deployment Guide

This guide describes how to deploy the PHX Trading System to a fresh Ubuntu VPS
for continuous operation.

## Prerequisites

- Ubuntu 22.04+ VPS
- At least 2GB RAM (4GB recommended)
- Docker & Docker Compose installed
- Git

## Step 1: Clone and Setup

```bash
git clone https://github.com/your-username/phx-trading.git
cd phx-trading
cp .env.prod.example .env.prod
```

## Step 2: Configure Environment

Edit `.env.prod` with your secure credentials:

- Set `DB_PASSWORD`
- Set `DASHBOARD_PASSWORD`
- Generate a `SECRET_KEY`

## Step 3: Initial Deployment

Run the automated deployment script:

```bash
chmod +x scripts/*.sh
./scripts/deploy_vps.sh
```

## Step 4: Verify

- **Dashboard**: Access via your VPS public IP (Port 80).
- **Metrics**: Check `http://<vps-ip>:8003/metrics` for internal stats.
- **Logs**: Monitor with `docker compose -f docker-compose.prod.yml logs -f`.

## Maintenance

- **Backups**: Set up a cron job for `scripts/backup_db.sh`.
- **Updates**: Re-run `./scripts/deploy_vps.sh`.
- **Cleanups**: The backup script automatically rotates files based on
  `ARTIFACT_RETENTION_DAYS`.

---

*Note: Ensure your VPS firewall (UFW) allows incoming traffic on port 80 (Public
UI) but restricts port 5432 (DB) and 6379 (Redis) to localhost only.*
