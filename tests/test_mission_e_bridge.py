import pytest
import uuid
from datetime import datetime, timezone, timedelta
from shared.database.session import SessionLocal, init_db
from shared.database.models import OrderTicket, TradeFillLog, TicketTradeLink, PositionSnapshot, Run, Packet
from shared.types.trade_capture import TradeFillEvent, PositionSnapshotBatch, TradeFillBatch
from shared.logic.trade_lifecycle import process_trade_fill
from shared.logic.sessions import get_nairobi_time

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()

@pytest.fixture
def db():
    session = SessionLocal()
    # Create a dummy run and packets for FKs
    run = Run(run_id=f"test-run-{uuid.uuid4().hex[:6]}")
    db_run = session.query(Run).first() or run
    if db_run == run:
        session.add(run)
        session.commit()
    
    p1 = Packet(run_id=db_run.id, packet_type="TechnicalSetupPacket", schema_version="1.0", data={})
    p2 = Packet(run_id=db_run.id, packet_type="RiskApprovalPacket", schema_version="1.0", data={})
    session.add_all([p1, p2])
    session.commit()
    
    yield session
    
    # Cleanup
    session.query(TicketTradeLink).delete()
    session.query(TradeFillLog).delete()
    session.query(PositionSnapshot).delete()
    session.query(OrderTicket).delete()
    session.commit()
    session.close()

def test_matching_logic_by_comment(db):
    # 1. Create a dummy ticket
    setup_p = db.query(Packet).filter(Packet.packet_type == "TechnicalSetupPacket").first()
    risk_p = db.query(Packet).filter(Packet.packet_type == "RiskApprovalPacket").first()
    
    ticket_id = f"T-{uuid.uuid4().hex[:8]}"
    ticket = OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=setup_p.id,
        risk_packet_id=risk_p.id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        status="APPROVED",
        idempotency_key=str(uuid.uuid4())
    )
    db.add(ticket)
    db.commit()

    # 2. Create a fill event with the ticket ID in comment
    fill = TradeFillEvent(
        broker_trade_id="BT-123",
        symbol="XAUUSD",
        side="BUY",
        lots=0.1,
        price=2000.5,
        time_utc=datetime.now(timezone.utc),
        time_eat=datetime.now(timezone.utc) + timedelta(hours=3),
        event_type="OPEN",
        comment=f"TICKET:{ticket_id}",
        account_id="ACC-001"
    )

    # 3. Process fill
    result = process_trade_fill(db, fill)
    assert result["status"] == "MATCHED"
    assert result["ticket_id"] == ticket_id

    # 4. Verify DB state
    updated_ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    assert updated_ticket.status == "EXECUTED"
    assert updated_ticket.executed_at is not None

def test_matching_logic_heuristic(db):
    # 1. Create a dummy ticket
    ticket_id = f"T-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    ticket = OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=2,
        risk_packet_id=2,
        pair="GBPUSD",
        direction="SELL",
        entry_price=1.25000,
        stop_loss=1.25500,
        take_profit_1=1.24000,
        lot_size=1.0,
        risk_usd=500.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        status="APPROVED",
        idempotency_key=str(uuid.uuid4()),
        created_at=now - timedelta(minutes=5)
    )
    db.add(ticket)
    db.commit()

    # 2. Create a fill event that should match heuristically (within time/price window)
    fill = TradeFillEvent(
        broker_trade_id="BT-456",
        symbol="GBPUSD",
        side="SELL",
        lots=1.0,
        price=1.25005,
        time_utc=now,
        time_eat=now + timedelta(hours=3),
        event_type="OPEN",
        comment="Random MT5 Comment",
        account_id="ACC-001"
    )

    # 3. Process fill
    result = process_trade_fill(db, fill)
    assert result["status"] == "MATCHED"
    assert result["ticket_id"] == ticket_id

def test_pnl_calculation_on_close(db):
    # 1. Setup executed ticket
    ticket_id = "T-PNL-TEST"
    ticket = OrderTicket(
        ticket_id=ticket_id,
        setup_packet_id=3,
        risk_packet_id=3,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,  # 20 points risk
        take_profit_1=2040.0,
        lot_size=1.0,
        risk_usd=2000.0,
        risk_pct=2.0,
        rr_tp1=2.0,
        status="EXECUTED",
        idempotency_key=str(uuid.uuid4())
    )
    db.add(ticket)
    db.commit()

    # 2. Link a trade
    link = TicketTradeLink(ticket_id=ticket_id, broker_trade_id="BT-PNL", match_method="DIRECT", confidence=1.0)
    db.add(link)
    db.commit()

    # 3. Close fill event
    close_fill = TradeFillEvent(
        broker_trade_id="BT-PNL-OUT",
        symbol="XAUUSD",
        side="SELL", # closing a buy
        lots=1.0,
        price=2030.0, # +30 points, should be 1.5R
        time_utc=datetime.now(timezone.utc),
        time_eat=datetime.now(timezone.utc) + timedelta(hours=3),
        event_type="CLOSE",
        comment="TICKET:T-PNL-TEST",
        account_id="ACC-001"
    )

    result = process_trade_fill(db, close_fill)
    assert result["status"] == "MATCHED"
    
    updated_ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    assert updated_ticket.status == "CLOSED"
    assert updated_ticket.manual_outcome_r is not None
    # Tolerance for small float diffs
    assert abs(updated_ticket.manual_outcome_r - 1.5) < 0.01 
