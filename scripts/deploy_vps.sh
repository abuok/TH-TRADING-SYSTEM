#!/bin/bash
# scripts/deploy_vps.sh
# Idempotent deployment script for Ubuntu VPS

set -e

echo "=== PHX Production Deployment Beginning ==="

# 1. Update Repo
echo "[1/5] Pulling latest changes..."
git pull origin main

# 2. Ensure ENV
if [ ! -f .env.prod ]; then
    echo "ERROR: .env.prod not found! Please create it from .env.prod.example"
    exit 1
fi

# 3. Pull & Build Stack
echo "[2/5] Building Docker stack..."
docker compose -f docker-compose.prod.yml build

# 4. Bring Up Stack
echo "[3/5] Starting services..."
docker compose -f docker-compose.prod.yml up -d

# 5. Run Migrations
echo "[4/5] Running database migrations..."
docker compose -f docker-compose.prod.yml exec orchestration alembic upgrade head

# 6. Cleanup
echo "[5/5] Cleaning up old images..."
docker image prune -f

echo "=== Deployment Successful ==="
echo "Dashboard live at: http://<vps-ip>"
