# Release Checklist

This checklist must be followed before any production release (merging to `main` or tagging a version).

- [ ] **Run All Tests**: `make test` must pass 100%.
- [ ] **Smoke Test**: Run `python scripts/smoke_test.py` to verify basic connectivity.
- [ ] **Migration Check**: `alembic check` or `migrate` should verify schema is up to date.
- [ ] **Backup Database**: Ensure a fresh backup of the production database exists.
- [ ] **Verify Authentication**: Log into the dashboard and verify `DASHBOARD_AUTH_ENABLED` is working.
- [ ] **Verify Bridge Freshness**: Check Live Data tab to ensure quotes are updating.
- [ ] **Review Proposals**: Ensure all Tuning proposals are either processed or intentionally left OPEN.
- [ ] **Check Graduation**: Verify the Pilot Scorecard status if moving from Pilot to Live.
- [ ] **Update Documentation**: Ensure `CHANGELOG.md` and `VERSION` are updated.
- [ ] **Git Tag**: Tag the commit with the version number (e.g., `git tag -a v1.0.0 -m "Release v1.0.0"`).
