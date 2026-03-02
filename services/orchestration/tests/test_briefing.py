"""
tests/test_briefing.py
Unit + integration tests for Session Briefing Pack assembly, delta computation,
and Dashboard rendering.  Uses in-memory SQLite + mocked Nairobi time.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import (
    Base,
    Packet,
    Run,
    KillSwitch,
    IncidentLog,
    OrderTicket,
    SessionBriefing,
)
from shared.types.briefing import BriefingPack
from shared.logic.briefing import (
    assemble_briefing,
    persist_briefing,
    render_briefing_html,
    _build_system_status,
    _build_market_context,
    _build_pair_overview,
    _build_delta,
)

# ──────────────────────────────────────────────
# In-memory DB fixture
# ──────────────────────────────────────────────

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

FIXED_NAIROBI = datetime(
    2026,
    2,
    26,
    12,
    0,
    0,  # London session (11:00–20:00 EAT)
    tzinfo=timezone(timedelta(hours=3)),
)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    # Need a Run row for Packet FKs
    run = Run(run_id="test-run-001")
    session.add(run)
    session.commit()
    session.refresh(run)
    session._test_run_id = run.id
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _add_packet(db, run_id, packet_type, data):
    p = Packet(
        run_id=run_id, packet_type=packet_type, schema_version="1.0.0", data=data
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ──────────────────────────────────────────────
# System Status tests
# ──────────────────────────────────────────────


def test_system_status_no_kill_switches(db):
    status = _build_system_status(db)
    assert status.active_kill_switches == []
    assert status.last_incident_summary is None


def test_system_status_with_kill_switch(db):
    db.add(KillSwitch(switch_type="HALT_PAIR", target="XAUUSD", is_active=1))
    db.commit()
    status = _build_system_status(db)
    assert "HALT_PAIR:XAUUSD" in status.active_kill_switches


def test_system_status_with_incident(db):
    db.add(IncidentLog(severity="ERROR", component="Risk", message="Daily loss hit"))
    db.commit()
    status = _build_system_status(db)
    assert "Daily loss hit" in status.last_incident_summary
    assert status.last_incident_severity == "ERROR"


# ──────────────────────────────────────────────
# Market Context tests
# ──────────────────────────────────────────────


def test_market_context_no_data(db):
    ctx = _build_market_context(db)
    assert ctx.is_stale is True
    assert ctx.high_impact_events == []


def test_market_context_fresh(db):
    _add_packet(
        db,
        db._test_run_id,
        "MarketContextPacket",
        {
            "asset_pair": "XAUUSD",
            "high_impact_events": [
                {"time": "15:30", "currency": "USD", "event": "NFP"}
            ],
            "no_trade_windows": [{"label": "NFP Window 15:15–15:45"}],
            "proxies": {},
            "metrics": {},
        },
    )
    ctx = _build_market_context(db)
    # SQLite returns created_at without tz; stale check treats it as UTC
    # The packet was just created, so it should be fresh (within 30-min TTL)
    assert len(ctx.high_impact_events) == 1
    assert ctx.high_impact_events[0]["event"] == "NFP"


# ──────────────────────────────────────────────
# Pair Overview tests
# ──────────────────────────────────────────────


def test_pair_overview_no_data(db):
    po = _build_pair_overview("XAUUSD", db)
    assert po.pair == "XAUUSD"
    assert po.bias == "unknown"
    assert po.latest_ticket is None
    assert len(po.stale_warnings) > 0


def test_pair_overview_with_setup(db):
    _add_packet(
        db,
        db._test_run_id,
        "TechnicalSetupPacket",
        {
            "asset_pair": "XAUUSD",
            "strategy_name": "PHX-S3",
            "stage": "S3",
            "score": 88.5,
            "entry_price": 2000.0,
            "stop_loss": 1990.0,
            "take_profit": 2030.0,
            "timeframe": "1H",
        },
    )
    po = _build_pair_overview("XAUUSD", db)
    assert "S3" in po.setup_count_by_stage
    assert len(po.top_setups) == 1
    assert po.top_setups[0].score == 88.5


def test_pair_overview_with_ticket(db):
    tkt = OrderTicket(
        ticket_id="TKT-TEST01",
        setup_packet_id=0,
        risk_packet_id=0,
        pair="GBPJPY",
        direction="SELL",
        entry_price=195.0,
        stop_loss=196.0,
        take_profit_1=193.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=0.5,
        rr_tp1=2.0,
        status="PENDING",
        idempotency_key="test-key-gbpjpy",
    )
    db.add(tkt)
    db.commit()
    po = _build_pair_overview("GBPJPY", db)
    assert po.latest_ticket is not None
    assert po.latest_ticket.ticket_id == "TKT-TEST01"


# ──────────────────────────────────────────────
# Full assemble_briefing() test
# ──────────────────────────────────────────────


def test_assemble_briefing_london(db):
    """Full pack assembly for a London session with minimal seeded data."""
    pack = assemble_briefing(db, now_nairobi=FIXED_NAIROBI, is_delta=False)

    assert isinstance(pack, BriefingPack)
    assert pack.session_label == "LONDON"
    assert pack.is_delta is False
    assert len(pack.pair_overviews) == 2
    assert any(po.pair == "XAUUSD" for po in pack.pair_overviews)
    assert any(po.pair == "GBPJPY" for po in pack.pair_overviews)
    assert len(pack.operator_actions) >= 1
    assert pack.risk_budget.max_daily_loss_pct > 0


def test_assemble_briefing_with_kill_switch_warning(db):
    db.add(KillSwitch(switch_type="HALT_ALL", is_active=1))
    db.commit()
    pack = assemble_briefing(db, now_nairobi=FIXED_NAIROBI)
    assert any("KILL SWITCH" in w for w in pack.global_warnings)
    assert any(
        a.priority == "HIGH" and "Kill switch" in a.description
        for a in pack.operator_actions
    )


# ──────────────────────────────────────────────
# Delta computation test
# ──────────────────────────────────────────────


def test_delta_first_briefing(db):
    delta = _build_delta(db, FIXED_NAIROBI, "LONDON")
    assert delta is not None
    assert "First briefing" in delta.summary


def test_delta_with_previous_briefing(db):
    # Seed a previous briefing
    prev = SessionBriefing(
        briefing_id="BRIEF-LO-20260226-093000-AAA",
        session_label="LONDON",
        date=FIXED_NAIROBI.date(),
        is_delta=False,
        data={"pair_overviews": []},
    )
    db.add(prev)
    db.commit()

    # Add a new ticket that wasn't in the previous briefing
    db.add(
        OrderTicket(
            ticket_id="TKT-NEW01",
            setup_packet_id=0,
            risk_packet_id=0,
            pair="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit_1=2030.0,
            lot_size=0.1,
            risk_usd=100.0,
            risk_pct=0.5,
            rr_tp1=3.0,
            status="PENDING",
            idempotency_key="delta-test-key",
        )
    )
    db.commit()

    delta = _build_delta(db, FIXED_NAIROBI, "LONDON")
    assert delta.previous_briefing_id == "BRIEF-LO-20260226-093000-AAA"
    assert "TKT-NEW01" in delta.new_tickets


# ──────────────────────────────────────────────
# HTML render test
# ──────────────────────────────────────────────


def test_render_briefing_html(db):
    pack = assemble_briefing(db, now_nairobi=FIXED_NAIROBI)
    html = render_briefing_html(pack)
    assert "Session Briefing Pack" in html
    assert "LONDON" in html
    assert "window.print()" in html
    assert "XAUUSD" in html
    assert "GBPJPY" in html


# ──────────────────────────────────────────────
# Persist test (checks DB + artifact file)
# ──────────────────────────────────────────────


def test_persist_briefing_creates_record(db, tmp_path, monkeypatch):
    # Redirect artifact output path to tmp_path so we don't write to project root
    monkeypatch.setattr(
        "shared.logic.briefing.BRIEFINGS_DIR", str(tmp_path / "artifacts" / "briefings")
    )
    pack = assemble_briefing(db, now_nairobi=FIXED_NAIROBI)
    record = persist_briefing(pack, db)

    assert record.briefing_id == pack.briefing_id
    assert record.html_path is not None

    # DB query
    found = (
        db.query(SessionBriefing)
        .filter(SessionBriefing.briefing_id == pack.briefing_id)
        .first()
    )
    assert found is not None
    assert found.session_label == "LONDON"


# ──────────────────────────────────────────────
# Integration: Dashboard route renders (import-level)
# ──────────────────────────────────────────────


def test_dashboard_briefings_route(db, tmp_path, monkeypatch):
    """Verify the FastAPI dashboard route returns 200 with briefings page."""
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    import shared.database.session as db_session

    # Override DB dependency to use our in-memory DB
    def override_get_db():
        yield db

    # Patch the logic helpers and service health check
    with (
        patch("services.dashboard.logic.get_briefings", return_value=[]),
        patch("services.dashboard.logic.get_latest_briefing", return_value=None),
        patch(
            "services.dashboard.logic.get_service_health",
            new_callable=AsyncMock,
            return_value=({}, {}),
        ),
    ):
        from services.dashboard.main import app as dash_app

        dash_app.dependency_overrides[db_session.get_db] = override_get_db
        client = TestClient(dash_app)
        response = client.get("/dashboard/briefings")
        dash_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "BRIEFINGS" in response.text.upper()
