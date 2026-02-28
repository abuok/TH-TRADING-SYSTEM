"""
tests/test_mission_dbridge.py
Unit and integration tests for Mission D: Live Data Bridge.
"""
import pytest
from fastapi.testclient import TestClient
from services.bridge.main import app as bridge_app
from shared.providers.price_quote import DBPriceQuoteProvider
from shared.providers.symbol_spec import DBSymbolSpecProvider
import shared.database.session as db_session
from shared.database.models import LiveQuote, SymbolSpec, OrderTicket
from shared.logic.trading_logic import generate_order_ticket
from services.orchestration.logic.execution_prep_generator import ExecutionPrepGenerator
from shared.logic.execution_logic import PreflightEngine

client = TestClient(bridge_app)

@pytest.fixture
def db():
    db = db_session.SessionLocal()
    # Cleanup
    db.query(LiveQuote).delete()
    db.query(SymbolSpec).delete()
    db.commit()
    yield db
    db.close()

def test_bridge_quote_ingestion(db):
    # Valid ingest
    payload = {"symbol": "XAUUSD", "bid": 2000.5, "ask": 2001.0, "ts_utc": "2026-02-28 12:00:00"}
    response = client.post("/bridge/quote", json=payload, headers={"X-Bridge-Secret": "change-me-in-prod"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["spread"] == 0.5

    # Idempotency check
    response = client.post("/bridge/quote", json=payload, headers={"X-Bridge-Secret": "change-me-in-prod"})
    assert response.json()["status"] == "ignored"

def test_bridge_spec_ingestion(db):
    payload = {
        "symbol": "XAUUSD",
        "contract_size": 100.0,
        "tick_size": 0.01,
        "tick_value": 0.01,
        "pip_size": 0.01,
        "min_lot": 0.01,
        "lot_step": 0.01
    }
    response = client.post("/bridge/spec", json=payload, headers={"X-Bridge-Secret": "change-me-in-prod"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_providers_from_db(db):
    # Seed data
    db.add(LiveQuote(symbol="XAUUSD", bid=2000.0, ask=2001.0, spread=1.0))
    db.add(SymbolSpec(symbol="XAUUSD", contract_size=100, tick_size=0.01, tick_value=0.01, pip_size=0.01, min_lot=0.01, lot_step=0.01))
    db.commit()

    price_provider = DBPriceQuoteProvider(db)
    quote = price_provider.get_quote("XAUUSD")
    assert quote.bid == 2000.0
    assert quote.mid == 2000.5

    spec_provider = DBSymbolSpecProvider(db)
    spec = spec_provider.get_spec("XAUUSD")
    assert spec.contract_size == 100

def test_preflight_fail_closed_on_no_data(db):
    # No data seeded
    engine = PreflightEngine(db)
    ticket = OrderTicket(pair="MISSING", entry_price=2000.0)
    
    # Force use of DB provider via env if needed (or just assume DB provider is used)
    import os
    os.environ["PRICE_PROVIDER"] = "db"
    
    try:
        checks = engine.run_checks(ticket)
        
        # Find price_deviation check
        pd_check = next(c for c in checks if c.id == "price_deviation")
        assert pd_check.status == "FAIL"
        assert "FAIL-CLOSED" in pd_check.details
    finally:
        os.environ["PRICE_PROVIDER"] = "mock"

def test_lot_sizing_with_spec(db):
    # Seed spec
    db.add(SymbolSpec(
        symbol="GBPJPY",
        contract_size=100000.0,
        tick_size=0.001,
        tick_value=0.01, # 0.01 USD per tick for 1 lot usually? No, depends on account denom. 
        pip_size=0.01,
        min_lot=0.01,
        lot_step=0.01
    ))
    db.commit()

    from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="GBPJPY",
        strategy_name="PHX",
        timeframe="1H",
        entry_price=180.0,
        stop_loss=179.0,
        take_profit=185.0
    )
    risk = RiskApprovalPacket(
        schema_version="1.0.0",
        asset_pair="GBPJPY",
        is_approved=True,
        risk_usd=100.0,
        risk_score=75.0,
        request_id="REQ_1",
        max_position_size=1.0,
        rr_ratio=3.0,
        approver="RiskEngine",
        status="ALLOW"
    )
    
    # Force spec provider to db
    import os
    os.environ["SPEC_PROVIDER"] = "db"
    
    try:
        ticket = generate_order_ticket(setup, risk, db)
        assert ticket.lot_size > 0
        assert ticket.status != "BLOCKED"
    finally:
        os.environ["SPEC_PROVIDER"] = "mock"

def test_lot_sizing_blocked_on_missing_spec(db):
    from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="UNKNOWN",
        strategy_name="PHX",
        timeframe="1H",
        entry_price=1.0,
        stop_loss=0.9,
        take_profit=1.1
    )
    risk = RiskApprovalPacket(
        schema_version="1.0.0",
        asset_pair="UNKNOWN",
        is_approved=True,
        risk_usd=100.0,
        risk_score=50.0,
        request_id="REQ_2",
        max_position_size=1.0,
        rr_ratio=2.0,
        approver="RiskEngine",
        status="ALLOW"
    )
    
    import os
    os.environ["SPEC_PROVIDER"] = "db"
    
    try:
        ticket = generate_order_ticket(setup, risk, db)
        assert ticket.status == "BLOCKED"
        assert "No SymbolSpec found" in ticket.block_reason
    finally:
        os.environ["SPEC_PROVIDER"] = "mock"
