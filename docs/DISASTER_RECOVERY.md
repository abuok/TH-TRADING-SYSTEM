# Disaster Recovery Playbook

Procedures for emergency response and system restoration.

## Restore Database (Postgres)

1. **Stop Services**: `docker-compose stop db`
2. **Restore from Dump**:

   ```bash
   cat backup_file.sql | docker exec -i trading_db psql -U user -d trading_db
   ```
3. **Restart Services**: `docker-compose up -d`
4. **Verify**: Check the **Tickets** dashboard for historical data.

## System Safe Mode (Kill Switch)

If the system exhibits erratic behavior (e.g., rapid-fire orders, disconnected
quotes):

1. **Trigger Global Kill Switch**:
   `python -m infra.cli kill-switch global --active 1`
2. **Broker-Level Stop**: Manually close all positions in the MT5 terminal if
   necessary.
3. **Investigate**: Check `incident_logs` table for error codes.

## Recover from Broken Migrations

If `alembic upgrade` fails or breaks the schema:

1. **Check Current Version**: `alembic current`
2. **Check History**: `alembic history`
3. **Rollback**: `alembic downgrade -1` (or to the last known stable
   `revision_id`).
4. **Verify Integrity**: Run `pytest tests/test_preflight_checks.py`.

## Secret Rotation

1. **Bridge Shared Secrets**: Update `BRIDGE_SECRET` in `.env` and restart both
   Bridge and Orchestrator.
2. **Dashboard Auth**: Update `DASHBOARD_PASSWORD` in `.env` and restart the
   dashboard service.

## Post-Recovery Verification

After any disaster recovery event, the following must be verified:

- [ ] `make release-check` passes.
- [ ] Dashboards are accessible and authenticated.
- [ ] Live Data bridge shows active price updates (no stale quotes).
- [ ] `OrderTicket` creation is successful (generate a mock ticket via CLI).
