"""
tests/test_chaos.py
-------------------
Chaos engineering tests — validates system resilience when dependencies fail.

Run:
    pytest tests/test_chaos.py -v -m chaos

These pass by demonstrating graceful degradation, not by succeeding normally.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── 1. Database commit failure → rollback ─────────────────────────────────────

@pytest.mark.chaos
def test_transaction_rollback_on_db_commit_error(db) -> None:  # type: ignore[no-untyped-def]
    """
    CHAOS: db.commit() raises mid-transaction.
    EXPECTED: row is NOT persisted; session remains usable after rollback.
    """
    from shared.database.models import KillSwitch

    ks = KillSwitch(switch_type="HALT_ALL", target="chaos-test", is_active=1)
    db.add(ks)

    with patch.object(db, "commit", side_effect=Exception("simulated commit failure")):
        try:
            db.commit()
        except Exception:
            db.rollback()

    found = db.query(KillSwitch).filter_by(target="chaos-test").first()
    assert found is None, "Rolled-back row must not be persisted"


# ── 2. AuditLog failure should not crash caller ───────────────────────────────

@pytest.mark.chaos
def test_audit_log_failure_does_not_propagate(db) -> None:  # type: ignore[no-untyped-def]
    """
    CHAOS: AuditLog DB insert explodes.
    EXPECTED: audit.audit_action() swallows the error and returns normally,
              so the calling trade operation is not disrupted.
    """
    from shared.logic.audit import audit_action

    with patch("shared.logic.audit.AuditLog", side_effect=Exception("DB unavailable")):
        # Must NOT raise
        audit_action(
            db=db,
            actor="chaos-test",
            action="TICKET_APPROVED",
            resource_type="OrderTicket",
            resource_id="chaos-ticket-001",
        )


# ── 3. Error hierarchy captures context ───────────────────────────────────────

@pytest.mark.chaos
def test_trading_system_error_context_preserved() -> None:
    """
    CHAOS: Verify that error context survives raise/except cycles.
    EXPECTED: error_code, context, and severity are accessible on caught exception.
    """
    from shared.types.errors import MarketDataError, TradingSystemError

    ctx = {"age_seconds": 420, "max_age_seconds": 300, "pair": "XAUUSD"}

    try:
        raise MarketDataError(
            message="Market data too stale",
            context=ctx,
        )
    except TradingSystemError as exc:
        assert exc.error_code == "MARKET_DATA_INVALID"
        assert exc.severity == "WARNING"
        assert exc.context["age_seconds"] == 420
        assert "stale" in exc.message


# ── 4. Pool health returns valid structure ────────────────────────────────────

@pytest.mark.chaos
def test_db_pool_health_returns_valid_shape() -> None:
    """
    CHAOS: Pool health endpoint must not crash and must return expected keys.
    """
    from shared.database.session import get_db_pool_health

    health = get_db_pool_health()

    required_keys = {
        "active_connections",
        "idle_connections",
        "total_pool_size",
        "max_pool_size",
        "overflow_used",
    }
    assert required_keys.issubset(health.keys()), f"Missing keys: {required_keys - health.keys()}"
    assert all(isinstance(v, int) for v in health.values()), "All values must be integers"
    assert health["active_connections"] >= 0
    assert health["total_pool_size"] >= 0
