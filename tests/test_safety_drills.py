import pytest
import redis
import datetime
import pytz
from datetime import timezone, timedelta, time as time_
from unittest.mock import patch
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from shared.messaging.event_bus import EventBus
from shared.providers.calendar import ForexFactoryCalendarProvider
from shared.logic.alignment import AlignmentEngine
from shared.database.models import IncidentLog, QuoteStaleLog, Base, ManagementSuggestionLog, OrderTicket, Run, Packet
import uuid

NAIROBI = pytz.timezone("Africa/Nairobi")

@pytest.fixture
def memory_db():
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
    Expected: publish() catches the ConnectionError, writes an IncidentLog, and fails gracefully.
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
    Scenario: QuoteStaleLog shows > 15s latency.
    Expected: AlignmentEngine hard-blocks execution.
    """
    pair = "XAUUSD"

    # 1. Insert a simulated quote stall metric (22.5 seconds stale)
    stale_log = QuoteStaleLog(
        symbol=pair,
        stale_duration_seconds=22.5,
        created_at=datetime.datetime.now(timezone.utc),
    )
    memory_db.add(stale_log)
    memory_db.commit()

    # 2. Evaluate the staleness rule directly
    cfg = {"quote_staleness_limit_seconds": 15.0}
    now_utc = datetime.datetime.now(timezone.utc)

    engine = AlignmentEngine()
    is_ok = engine._check_quote_staleness(pair, memory_db, now_utc, cfg)

    # 3. Assert fail-closed posture
    assert is_ok is False


def test_drill_missing_calendar_feed_fail_closed():
    """
    DRILL: Missing Calendar Feed
    Expected: fetch_events throws a RuntimeError.
    """
    provider = ForexFactoryCalendarProvider()

    with patch("feedparser.parse", side_effect=Exception("Connection Reset by Peer")):
        with pytest.raises(RuntimeError) as exc_info:
            provider.fetch_events()

        assert "Calendar fetch failed" in str(exc_info.value)


def test_drill_db_concurrent_lock_handling(memory_db):
    """
    DRILL: DB Concurrent Locks
    Expected: IntegrityError is raised and caught.
    """
    from sqlalchemy.exc import IntegrityError

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


def test_drill_bridge_offline_no_logs_fail_closed(memory_db):
    """
    DRILL: Bridge Offline — No QuoteStaleLog records.
    Expected: Must FAIL (fail-closed).
    """
    pair = "GBPJPY"
    cfg = {"quote_staleness_limit_seconds": 15.0}
    now_utc = datetime.datetime.now(timezone.utc)

    engine = AlignmentEngine()
    is_ok = engine._check_quote_staleness(pair, memory_db, now_utc, cfg)

    assert is_ok is False


def test_rule_news_window_midnight_crossover():
    """
    DRILL: News event at 00:30 EAT detected when current time is 23:50 EAT.
    """
    # Simulate: current time is 23:50 EAT on Wednesday
    now = NAIROBI.localize(
        datetime.datetime(2026, 3, 4, 23, 50, 0)
    )

    # Event is at 00:30 (early morning — 40 min away, on the next calendar day)
    context_data = {
        "high_impact_events": [
            {"time": "00:30", "event": "FOMC", "impact": "HIGH"}
        ]
    }
    
    engine = AlignmentEngine()
    is_ok = engine._check_event_proximity(context_data, now, engine.cfg)
    assert is_ok is False, "Should block 40m before midnight-crossing event"

    # Event is 1 hour away (00:55) - 65 minutes total
    context_data_safe = {
        "high_impact_events": [
            {"time": "00:55", "event": "FOMC", "impact": "HIGH"}
        ]
    }
    is_ok_safe = engine._check_event_proximity(context_data_safe, now, engine.cfg)
    assert is_ok_safe is True, "Should allow 65m before midnight-crossing event"
