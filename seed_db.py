import os
import sys
from datetime import datetime, timezone, timedelta

os.environ["DATABASE_URL"] = "sqlite:///trading_db.sqlite"

# Ensure shared is importable
sys.path.append(os.getcwd())

from shared.database.session import engine, SessionLocal, init_db
from shared.database.models import LiveQuote, SymbolSpec, Packet, Run, KillSwitch, IncidentLog

def seed():
    print("Initializing Database...")
    init_db()
    db = SessionLocal()
    
    # Check if we already have data
    if db.query(LiveQuote).first():
        print("Data already exists. Skipping seed.")
        return

    print("Seeding data...")
    
    # 1. Run
    run = Run(run_id="DEMO-RUN-001", status="running")
    db.add(run)
    db.flush()
    
    # 2. Market Context Packet
    ctx_packet = Packet(
        run_id=run.id,
        packet_type="MarketContextPacket",
        schema_version="1.0.0",
        data={
            "high_impact_events": [
                {"event": "Non-Farm Payrolls", "time": "2026-03-01T15:30:00Z", "impact": "HIGH"},
                {"event": "FOMC Meeting", "time": "2026-03-05T21:00:00Z", "impact": "HIGH"}
            ],
            "no_trade_windows": [
                {"start": "2026-03-01T15:15:00Z", "end": "2026-03-01T15:45:00Z", "reason": "NFP Release"}
            ]
        }
    )
    db.add(ctx_packet)
    
    # 3. Live Quotes
    quotes = [
        LiveQuote(symbol="XAUUSD", bid=2034.50, ask=2034.85, spread=0.35, raw_timestamp="2026-02-28T12:00:00Z"),
        LiveQuote(symbol="EURUSD", bid=1.08450, ask=1.08462, spread=0.12, raw_timestamp="2026-02-28T12:00:01Z"),
        LiveQuote(symbol="GBPJPY", bid=190.25, ask=190.30, spread=0.05, raw_timestamp="2026-02-28T12:00:02Z")
    ]
    db.add_all(quotes)
    
    # 4. Symbol Specs
    specs = [
        SymbolSpec(symbol="XAUUSD", contract_size=100.0, tick_size=0.01, tick_value=1.0, pip_size=0.1, min_lot=0.01, lot_step=0.01),
        SymbolSpec(symbol="EURUSD", contract_size=100000.0, tick_size=0.00001, tick_value=1.0, pip_size=0.0001, min_lot=0.01, lot_step=0.01),
        SymbolSpec(symbol="GBPJPY", contract_size=100000.0, tick_size=0.001, tick_value=10.0, pip_size=0.01, min_lot=0.01, lot_step=0.01)
    ]
    db.add_all(specs)
    
    # 5. Technical Setup Packets (Fresh and Stale)
    now = datetime.now(timezone.utc)
    setups = [
        Packet(run_id=run.id, packet_type="TechnicalSetupPacket", schema_version="1.0.0", created_at=now, data={"asset_pair": "XAUUSD", "stage": "BREAKOUT", "score": 85.0}),
        Packet(run_id=run.id, packet_type="TechnicalSetupPacket", schema_version="1.0.0", created_at=now - timedelta(seconds=120), data={"asset_pair": "EURUSD", "stage": "PULLBACK", "score": 70.0}),
    ]
    db.add_all(setups)
    
    # 6. Risk Decisions
    decisions = [
        Packet(run_id=run.id, packet_type="RiskApprovalPacket", schema_version="1.0.0", data={"asset_pair": "XAUUSD", "action": "ALLOW", "reason": "Risk limits OK"}),
    ]
    db.add_all(decisions)
    
    # 7. Incidents
    incidents = [
        IncidentLog(severity="INFO", component="Bridge", message="Live Data Bridge service connected."),
        IncidentLog(severity="WARNING", component="Bridge", message="Slow response from MT5 detected (300ms).")
    ]
    db.add_all(incidents)
    
    db.commit()
    print("Seed complete.")

if __name__ == "__main__":
    seed()
