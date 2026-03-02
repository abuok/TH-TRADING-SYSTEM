import os
import sys
from datetime import datetime, timezone, timedelta

os.environ["DATABASE_URL"] = "sqlite:///trading_db.sqlite"

# Ensure shared is importable
sys.path.append(os.getcwd())

from shared.database.session import SessionLocal, init_db
from shared.database.models import (
    LiveQuote,
    SymbolSpec,
    Packet,
    Run,
    IncidentLog,
    OrderTicket,
    HindsightOutcomeLog,
    PolicySelectionLog,
)


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
                {
                    "event": "Non-Farm Payrolls",
                    "time": "2026-03-01T15:30:00Z",
                    "impact": "HIGH",
                },
                {
                    "event": "FOMC Meeting",
                    "time": "2026-03-05T21:00:00Z",
                    "impact": "HIGH",
                },
            ],
            "no_trade_windows": [
                {
                    "start": "2026-03-01T15:15:00Z",
                    "end": "2026-03-01T15:45:00Z",
                    "reason": "NFP Release",
                }
            ],
        },
    )
    db.add(ctx_packet)

    # 3. Live Quotes
    quotes = [
        LiveQuote(
            symbol="XAUUSD",
            bid=2034.50,
            ask=2034.85,
            spread=0.35,
            raw_timestamp="2026-02-28T12:00:00Z",
        ),
        LiveQuote(
            symbol="EURUSD",
            bid=1.08450,
            ask=1.08462,
            spread=0.12,
            raw_timestamp="2026-02-28T12:00:01Z",
        ),
        LiveQuote(
            symbol="GBPJPY",
            bid=190.25,
            ask=190.30,
            spread=0.05,
            raw_timestamp="2026-02-28T12:00:02Z",
        ),
    ]
    db.add_all(quotes)

    # 4. Symbol Specs
    specs = [
        SymbolSpec(
            symbol="XAUUSD",
            contract_size=100.0,
            tick_size=0.01,
            tick_value=1.0,
            pip_size=0.1,
            min_lot=0.01,
            lot_step=0.01,
        ),
        SymbolSpec(
            symbol="EURUSD",
            contract_size=100000.0,
            tick_size=0.00001,
            tick_value=1.0,
            pip_size=0.0001,
            min_lot=0.01,
            lot_step=0.01,
        ),
        SymbolSpec(
            symbol="GBPJPY",
            contract_size=100000.0,
            tick_size=0.001,
            tick_value=10.0,
            pip_size=0.01,
            min_lot=0.01,
            lot_step=0.01,
        ),
    ]
    db.add_all(specs)

    # 5. Technical Setup Packets (Fresh and Stale)
    now = datetime.now(timezone.utc)
    setups = [
        Packet(
            run_id=run.id,
            packet_type="TechnicalSetupPacket",
            schema_version="1.0.0",
            created_at=now,
            data={"asset_pair": "XAUUSD", "stage": "BREAKOUT", "score": 85.0},
        ),
        Packet(
            run_id=run.id,
            packet_type="TechnicalSetupPacket",
            schema_version="1.0.0",
            created_at=now - timedelta(seconds=120),
            data={"asset_pair": "EURUSD", "stage": "PULLBACK", "score": 70.0},
        ),
    ]
    db.add_all(setups)

    # 6. Risk Decisions
    decisions = [
        Packet(
            run_id=run.id,
            packet_type="RiskApprovalPacket",
            schema_version="1.0.0",
            data={
                "asset_pair": "XAUUSD",
                "action": "ALLOW",
                "reason": "Risk limits OK",
            },
        ),
    ]
    db.add_all(decisions)

    # 7. Incidents
    incidents = [
        IncidentLog(
            severity="INFO",
            component="Bridge",
            message="Live Data Bridge service connected.",
        ),
        IncidentLog(
            severity="WARNING",
            component="Bridge",
            message="Slow response from MT5 detected (300ms).",
        ),
    ]
    db.add_all(incidents)
    db.flush()

    # 8. Order Tickets (for Hindsight)
    ticket = OrderTicket(
        ticket_id="TKT-RESEARCH-001",
        setup_packet_id=setups[0].id,
        risk_packet_id=decisions[0].id,
        pair="XAUUSD",
        direction="BUY",
        entry_price=2034.50,
        stop_loss=2030.00,
        take_profit_1=2045.00,
        lot_size=0.1,
        risk_usd=45.0,
        risk_pct=0.45,
        rr_tp1=2.3,
        status="SKIPPED",
        skip_reason="NEWS_WINDOW",
        idempotency_key="ORDER_IDEMP_001",
        hindsight_status="DONE",
        hindsight_outcome_label="WIN",
        hindsight_realized_r=2.3,
    )
    db.add(ticket)
    db.flush()

    # 9. Hindsight Outcome Log
    hindsight_log = HindsightOutcomeLog(
        ticket_id=ticket.ticket_id,
        outcome_label="WIN",
        realized_r=2.3,
        first_hit="TP1",
        time_to_hit_min=45,
        notes="Price hit TP1 after 45 mins. Good setup missed.",
    )
    db.add(hindsight_log)

    # 10. Policy Selection Log
    policies = [
        PolicySelectionLog(
            pair="XAUUSD",
            policy_name="Volatile_Breakout_V2",
            policy_hash="abc123hash",
            reasons={"volatility": "high", "trend": "strong_up"},
            regime_signals={"atr_ratio": 1.5, "adx": 35},
        ),
        PolicySelectionLog(
            pair="EURUSD",
            policy_name="Mean_Reversion_Standard",
            policy_hash="xyz789hash",
            reasons={"volatility": "low", "regime": "ranging"},
            regime_signals={"atr_ratio": 0.8, "rsi": 50},
        ),
    ]
    db.add_all(policies)

    db.commit()
    print("Seed complete.")

    # 11. Create dummy research artifacts
    print("Creating research artifacts...")
    os.makedirs("artifacts/research", exist_ok=True)
    import json

    run_id = "res_demo_001"
    research_report = {
        "run_id": run_id,
        "strategy": "PHX_Detector_V3",
        "dataset": "XAUUSD_M1_2024",
        "net_profit": 1250.50,
        "win_rate": 0.62,
        "max_drawdown": 0.05,
        "sharpe_ratio": 1.8,
        "total_trades": 142,
    }
    with open(f"artifacts/research/{run_id}.json", "w") as f:
        json.dump(research_report, f)

    with open(f"artifacts/research/{run_id}.html", "w") as f:
        f.write(
            f"<html><body><h1>Research Report: {run_id}</h1><p>Performance: +12.5% over 1 month.</p></body></html>"
        )

    # Create a dummy data.csv for hindsight
    if not os.path.exists("data.csv"):
        with open("data.csv", "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2026-02-28 12:00:00,2034.5,2035.0,2034.0,2034.8,100\n")


if __name__ == "__main__":
    seed()
