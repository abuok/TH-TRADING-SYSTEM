#!/bin/bash
# scripts/backup_db.sh
# Periodic Postgres backup for PHX monorepo

set -e

BACKUP_DIR="artifacts/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/phx_db_${TIMESTAMP}.sql"
RETENTION_DAYS=${ARTIFACT_RETENTION_DAYS:-30}

mkdir -p "${BACKUP_DIR}"

echo "Starting database backup to ${BACKUP_FILE}..."

# Run pg_dump within the prod container
docker compose -f docker-compose.prod.yml exec -t db pg_dump -U phx_prod_user phx_trading_prod > "${BACKUP_FILE}"

echo "Backup complete. Success."

# Rotation
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "phx_db_*.sql" -mtime +"${RETENTION_DAYS}" -delete

echo "Data maintenance finished."
