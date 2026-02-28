import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(os.getcwd())

from shared.database.models import Base, OrderTicket, HindsightOutcomeLog, GuardrailsLog, Packet, Run
from services.orchestration.logic.ops_engine import OpsEngine
from services.orchestration.logic.review_engine import ReviewEngine
from shared.logic.sessions import get_nairobi_time

# Setup mock database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_reporting.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_test_data(db):
    Base.metadata.create_all(bind=engine)
    now = get_nairobi_time()
    
    # Create a Run first
    run = Run(run_id="run_1", status="completed")
    db.add(run)
    db.flush() # Get run.id

    # 1. Market Context Packet with News
    context_data = {
        "high_impact_events": [
            {"event": "BOE Interest Rate Decision", "time": (now + timedelta(hours=2)).isoformat()},
            {"event": "Non-Farm Payrolls", "time": (now + timedelta(hours=24)).isoformat()}
        ],
        "no_trade_windows": [
            {"event": "BOE Interest Rate Decision", "start": (now - timedelta(minutes=30)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
        ]
    }
    p = Packet(
        run_id=run.id,
        packet_type="MarketContextPacket", 
        data=context_data, 
        created_at=now,
        schema_version="1.0"
    )
    db.add(p)
    
    # 2. Winning Trade with Guardrails Log
    t = OrderTicket(
        ticket_id="TICKET_1",
        setup_packet_id=1,
        risk_packet_id=1,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit_1=2020.0,
        lot_size=0.1,
        risk_usd=100.0,
        risk_pct=1.0,
        rr_tp1=2.0,
        idempotency_key="key_1",
        status="APPROVED",
        manual_outcome_label="WIN",
        manual_outcome_r=2.5,
        created_at=now - timedelta(days=2)
    )
    db.add(t)
    
    h = HindsightOutcomeLog(
        ticket_id="TICKET_1",
        outcome_label="WIN",
        realized_r=2.5,
        first_hit="TP1",
        computed_at=now - timedelta(days=1)
    )
    db.add(h)
    
    g = GuardrailsLog(
        setup_packet_id=1, # Mocking ID 1 as if it were setup_123
        hard_block=False,
        created_at=now - timedelta(days=2),
        pair="XAUUSD",
        discipline_score=92,
        result_json={}
    )
    db.add(g)
    
    # 3. Violation
    v = GuardrailsLog(
        setup_packet_id=2,
        hard_block=True,
        created_at=now - timedelta(days=3),
        pair="XAUUSD",
        discipline_score=45,
        result_json={}
    )
    db.add(v)
    
    db.commit()

def verify():
    db = TestingSessionLocal()
    try:
        setup_test_data(db)
        
        # Test OpsEngine
        ops = OpsEngine(db)
        report, _ = ops.generate_daily_report()
        
        print("\n--- Daily Ops Report Verification ---")
        print(f"Checklist Do: {report.checklist_do}")
        print(f"Checklist Don't: {report.checklist_dont}")
        
        # Check if BOE is in checklist_dont
        assert any("BOE Interest Rate Decision" in item for item in report.checklist_dont), "News not found in checklist_dont"
        print("PASS: Dynamic news checklist verified.")

        # Test ReviewEngine
        review = ReviewEngine(db)
        report_w = review.generate_weekly_report()
        
        print("\n--- Weekly Review Verification ---")
        print(f"Avg Winner Score: {report_w.avg_guardrails_score}")
        print(f"Violations: {report_w.rule_violations_count}")
        
        # Verify metrics
        assert report_w.avg_guardrails_score == 92.0, f"Expected 92.0, got {report_w.avg_guardrails_score}"
        assert report_w.rule_violations_count == 1, f"Expected 1 violation, got {report_w.rule_violations_count}"
        print("PASS: Real metrics verified.")

    finally:
        db.close()
        if os.path.exists("test_reporting.db"):
            os.remove("test_reporting.db")

if __name__ == "__main__":
    verify()
