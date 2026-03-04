import pytest
import redis
import datetime
from unittest.mock import patch

from shared.messaging.event_bus import EventBus
from shared.providers.calendar import ForexFactoryCalendarProvider
from shared.logic.guardrails import _rule_quote_staleness
from shared.database.models import IncidentLog, QuoteStaleLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def memory_db():
    from shared.database.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


def test_drill_redis_disconnect_graceful_degradation(memory_db):
    """
    DRILL: Redis Disconnects
    Scenario: EventBus cannot reach Redis cluster.
    Expected: publish() catches the ConnectionError, writes an IncidentLog, and fails gracefully without crashing the runner.
    """
    bus = EventBus()

    # Mock the internal client to simulate total connection failure
    with patch.object(
        bus.client,
        "xadd",
        side_effect=redis.exceptions.ConnectionError("Connection refused"),
    ):
        # We also need to patch the sessionmaker to use our memory_db for the IncidentLog
        with patch("shared.database.session.SessionLocal", return_value=memory_db):
            result = bus.publish("test_stream", {"foo": "bar"}, retries=2)

            # Should fail gracefully and return None
            assert result is None

            # Should have created a CRITICAL IncidentLog
            incident = (
                memory_db.query(IncidentLog).filter_by(component="EventBus").first()
            )
            assert incident is not None
            assert incident.severity == "CRITICAL"
            assert "Failed to publish" in incident.message


def test_drill_mt5_bridge_latency_staleness_guardrail(memory_db):
    """
    DRILL: MT5 Bridge Latency
    Scenario: MT5 is disconnected or lagging heavily, QuoteStaleLog shows > 15s latency.
    Expected: Guardrails engine invokes the staleness rule and hard-blocks execution.
    """
    from datetime import timezone

    pair = "XAUUSD"

    # 1. Insert a simulated quote stall metric (20 seconds stale)
    stale_log = QuoteStaleLog(
        symbol=pair,
        stale_duration_seconds=22.5,
        created_at=datetime.datetime.now(timezone.utc),
    )
    memory_db.add(stale_log)
    memory_db.commit()

    # 2. Evaluate the staleness rule directly
    setup_data = {"asset_pair": pair}
    cfg = {"quote_staleness_limit_seconds": 15.0}  # 15s limit

    rule_check = _rule_quote_staleness(setup_data, cfg, memory_db)

    # 3. Assert fail-closed posture
    assert rule_check.status == "FAIL"
    assert rule_check.is_mandatory is True
    assert "22.5s > limit 15.0s" in rule_check.details


def test_drill_missing_calendar_feed_fail_closed():
    """
    DRILL: Missing Calendar Feed
    Scenario: The ForexFactory RSS XML stream is offline or returning 500.
    Expected: fetch_events throws a RuntimeError instead of returning [], causing ingestion to halt and fail-closed over time due to staleness.
    """
    provider = ForexFactoryCalendarProvider()

    with patch("feedparser.parse", side_effect=Exception("Connection Reset by Peer")):
        with pytest.raises(RuntimeError) as exc_info:
            provider.fetch_events()

        assert "Calendar fetch failed" in str(exc_info.value)


def test_drill_db_concurrent_lock_handling(memory_db):
    """
    DRILL: DB Concurrent Locks
    Scenario: Two inserts race on a UniqueConstraint column.
    Expected: IntegrityError is raised and caught, no ghost row is committed.
    """
    from sqlalchemy.exc import IntegrityError
    from shared.database.models import QuoteStaleLog
    import datetime
    from datetime import timezone

    # Insert a QuoteStaleLog row first
    row1 = QuoteStaleLog(
        symbol="GBPJPY",
        stale_duration_seconds=5.0,
        created_at=datetime.datetime.now(timezone.utc),
    )
    memory_db.add(row1)
    memory_db.commit()

    # Attempt a duplicate via ManagementSuggestionLog UniqueConstraint
    from shared.database.models import ManagementSuggestionLog, OrderTicket, Run, Packet
    import uuid

    # Set up the minimum required FK chain
    run = Run(run_id=str(uuid.uuid4()), status="running")
    memory_db.add(run)
    memory_db.commit()

    pkt = Packet(
        run_id=run.id,
        packet_type="TechnicalSetupPacket",
        schema_version="1.0.0",
        data={},
    )
    memory_db.add(pkt)
    memory_db.commit()

    ticket = OrderTicket(
        ticket_id=f"TKT-{uuid.uuid4().hex[:8]}",
        setup_packet_id=pkt.id,
        risk_packet_id=pkt.id,
        pair="GBPJPY",
        direction="BUY",
        entry_price=190.0,
        stop_loss=189.5,
        take_profit_1=191.0,
        lot_size=0.01,
        risk_usd=50.0,
        risk_pct=2.0,
        rr_tp1=2.0,
        idempotency_key=str(uuid.uuid4()),
    )
    memory_db.add(ticket)
    memory_db.commit()

    bucket = "2026-01-01-10"
    sug1 = ManagementSuggestionLog(
        ticket_id=ticket.ticket_id,
        broker_trade_id="BRK001",
        suggestion_type="MOVE_SL_TO_BE",
        severity="WARN",
        data={},
        time_bucket=bucket,
        expires_at=datetime.datetime.now(timezone.utc),
    )
    memory_db.add(sug1)
    memory_db.commit()

    # Attempt a second insert with the same (ticket_id, suggestion_type, time_bucket)
    sug2 = ManagementSuggestionLog(
        ticket_id=ticket.ticket_id,
        broker_trade_id="BRK001",
        suggestion_type="MOVE_SL_TO_BE",
        severity="WARN",
        data={},
        time_bucket=bucket,
        expires_at=datetime.datetime.now(timezone.utc),
    )
    memory_db.add(sug2)
    with pytest.raises(IntegrityError):
        memory_db.commit()

    memory_db.rollback()  # clean up for test isolation


def test_drill_bridge_offline_no_logs_fail_closed(memory_db):
    """
    DRILL: Bridge Offline — No QuoteStaleLog records.
    Scenario: MT5 bridge has never logged any staleness data for a pair.
    Expected: GR-Q01 must FAIL (fail-closed), NOT pass with 0.0s staleness.
    This is the regression test for the false-pass bug fixed in guardrails.py.
    """
    from shared.logic.guardrails import _rule_quote_staleness

    pair = "GBPJPY"
    setup_data = {"asset_pair": pair}
    cfg = {"quote_staleness_limit_seconds": 15.0, "score_deduction_fail": 20}

    # No QuoteStaleLog rows inserted — simulates bridge never having connected
    rule_check = _rule_quote_staleness(setup_data, cfg, memory_db)

    assert rule_check.status == "FAIL", (
        f"GR-Q01 must FAIL when bridge is offline (no log records). Got: {rule_check.status}"
    )
    assert rule_check.is_mandatory is True
    assert "FAIL-CLOSED" in rule_check.details
    assert pair in rule_check.details


def test_rule_news_window_midnight_crossover():
    """
    DRILL: News event at 00:30 EAT detected when current time is 23:50 EAT.
    This is the regression test for the midnight date-boundary bug fixed in guardrails.py.
    """
    import pytz
    from shared.logic.guardrails import _rule_news_window

    NAIROBI = pytz.timezone("Africa/Nairobi")

    # Simulate: current time is 23:50 EAT
    now = NAIROBI.localize(
        datetime.datetime(2026, 3, 4, 23, 50, 0)  # 23:50 EAT
    )

    # Event is at 00:30 (early morning — 40 min away, on the next calendar day)
    cfg = {
        "news_buffer_minutes": 60,  # 60-min buffer — should catch 40-min-away event
        "news_window_hard_block": True,
        "score_deduction_fail": 20,
    }
    context_data = {
        "high_impact_events": [
            {"time": "00:30", "event": "FOMC Minutes", "currency": "USD"}
        ]
    }

    result = _rule_news_window(now, cfg, context_data)

    assert result.status == "FAIL", (
        f"GR-N01 must FAIL: event at 00:30 is only 40 min away from 23:50. Got: {result.status}. "
        f"Details: {result.details}"
    )
    assert "FOMC Minutes" in result.details
