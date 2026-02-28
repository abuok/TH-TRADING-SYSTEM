import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.models import Base, OrderTicket, PositionSnapshot, TicketTradeLink, ManagementSuggestionLog, LiveQuote, Packet, Run
from shared.logic.trade_management_engine import run_management_cycle
from shared.providers.price_quote import MockPriceQuoteProvider, set_price_quote_provider

# Setup in-memory SQLite for testing
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def test_move_sl_to_be_suggestion(db):
    # 1. Setup Mock Provider
    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)
    
    # 2. Seed Data
    run = Run(run_id="R1")
    db.add(run)
    db.flush()
    
    p1 = Packet(run_id=run.id, packet_type="SetupPacket", schema_version="2.0", data={"pair": "EURUSD"})
    db.add(p1)
    db.flush()
    
    # Ticket at 1.00000, SL at 0.99900 (10 pips risk)
    ticket = OrderTicket(
        ticket_id="T1",
        setup_packet_id=p1.id,
        risk_packet_id=p1.id,
        pair="EURUSD",
        direction="BUY",
        entry_price=1.00000,
        stop_loss=0.99900,
        take_profit_1=1.00200,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T1_KEY",
        status="APPROVED"
    )
    db.add(ticket)
    db.flush()
    
    # Position linked to T1
    pos = PositionSnapshot(
        position_id=12345,
        symbol="EURUSD",
        side="BUY",
        lots=0.1,
        avg_price=1.00000,
        sl=0.99900,
        tp=1.00200,
        updated_at_utc=datetime.now(timezone.utc)
    )
    db.add(pos)
    
    link = TicketTradeLink(ticket_id="T1", broker_trade_id=12345)
    db.add(link)
    db.commit()
    
    # 3. Scenario: Price is at 1.00100 (which is 1.0R)
    mock_quotes.set_quote("EURUSD", 1.00100, 1.00101)
    
    # 4. Run Cycle
    run_management_cycle(db)
    
    # 5. Assert suggestion created
    sug = db.query(ManagementSuggestionLog).first()
    assert sug is not None
    assert sug.suggestion_type == "MOVE_SL_TO_BE"
    assert sug.data["current_r"] == 1.0
    assert "Move SL to Entry" in sug.data["instruction"]

def test_tp1_partial_suggestion(db):
    # 1. Setup Mock Provider
    mock_quotes = MockPriceQuoteProvider()
    set_price_quote_provider(mock_quotes)
    
    # 2. Seed Data
    run = Run(run_id="R2")
    db.add(run)
    db.flush()
    
    p2 = Packet(run_id=run.id, packet_type="SetupPacket", schema_version="2.0", data={"pair": "GBPUSD"})
    db.add(p2)
    db.flush()
    
    ticket = OrderTicket(
        ticket_id="T2",
        setup_packet_id=p2.id,
        risk_packet_id=p2.id,
        pair="GBPUSD",
        direction="BUY",
        entry_price=1.30000,
        stop_loss=1.29900,
        take_profit_1=1.30200, # TP1 at 2.0R
        lot_size=0.2,
        risk_usd=200.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="T2_KEY",
        status="APPROVED"
    )
    db.add(ticket)
    db.flush()
    
    pos = PositionSnapshot(
        position_id=67890,
        symbol="GBPUSD",
        side="BUY",
        lots=0.2,
        avg_price=1.30000,
        sl=1.29900,
        tp=1.30400,
        updated_at_utc=datetime.now(timezone.utc)
    )
    db.add(pos)
    
    link = TicketTradeLink(ticket_id="T2", broker_trade_id=67890)
    db.add(link)
    db.commit()
    
    # 3. Scenario: Price is at 1.30200 (Hit TP1)
    mock_quotes.set_quote("GBPUSD", 1.30200, 1.30201)
    
    # 4. Run Cycle
    run_management_cycle(db)
    
    # 5. Assert
    sug = db.query(ManagementSuggestionLog).filter(ManagementSuggestionLog.suggestion_type == "TAKE_PARTIAL_TP1").first()
    assert sug is not None
    assert "0.10 lots" in sug.data["instruction"]
