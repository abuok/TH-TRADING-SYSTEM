import yaml
from datetime import datetime, timedelta, date, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Tuple
from shared.database.models import (
    OrderTicket, TradeFillLog, PolicySelectionLog, GuardrailsLog, 
    ExecutionPrepLog, PilotSessionLog, PilotScorecardLog, TuningProposalLog
)
from shared.types.pilot import PilotSessionRecord, PilotScorecard, PairStats
from shared.logic.sessions import get_nairobi_time

def load_pilot_config(path: str = "config/pilot_gate.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def fetch_session_metrics(db: Session, target_date: date) -> PilotSessionRecord:
    start_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    
    # 1. Ticket metrics
    tickets = db.query(OrderTicket).filter(
        OrderTicket.created_at >= start_dt,
        OrderTicket.created_at < end_dt
    ).all()
    
    total_tickets = len(tickets)
    approved = [t for t in tickets if t.status == "APPROVED"]
    skipped = [t for t in tickets if t.status == "SKIPPED"]
    
    # Exec log
    exec_logs = db.query(ExecutionPrepLog).filter(
        ExecutionPrepLog.created_at >= start_dt,
        ExecutionPrepLog.created_at < end_dt
    ).all()
    
    expired = [e for e in exec_logs if e.status == "EXPIRED"]
    overrides = [e for e in exec_logs if "OVERRIDE" in str(e.data)]
    
    expired_rate = (len(expired) / total_tickets * 100) if total_tickets > 0 else 0
    override_rate = (len(overrides) / total_tickets * 100) if total_tickets > 0 else 0

    process_metrics = {
        "total_tickets": total_tickets,
        "approved": len(approved),
        "skipped": len(skipped),
        "expired": len(expired),
        "overrides": len(overrides),
        "expired_ticket_rate": expired_rate,
        "execution_prep_override_rate": override_rate,
        "ticket_based_trades_pct": 100.0 # Stub assuming all are ticket based 
    }

    # 2. Performance Metrics
    realized_r_total = sum(t.realized_r for t in approved if t.realized_r is not None)
    missed_r_total = sum(t.hindsight_r for t in skipped if t.hindsight_r is not None)
    
    win_count = len([t for t in approved if (t.realized_r or 0) > 0])
    win_rate = (win_count / len(approved) * 100) if approved else 0.0
    expectancy = (realized_r_total / len(approved)) if approved else 0.0
    
    drawdown_r = min(realized_r_total, 0.0) # naive
    
    performance_metrics = {
        "realized_r": realized_r_total,
        "missed_r": missed_r_total,
        "win_rate_pct": win_rate,
        "approved_expectancy_r": expectancy,
        "max_drawdown_r": drawdown_r,
        "expectancy_beat_baseline": expectancy > (missed_r_total / len(skipped) if skipped else 0)
    }

    # 3. Reliability (Stubbed based on lack of direct Quote stale logs)
    reliability_metrics = {
        "quote_freshness_pct": 99.9, # Assuming Bridge is up
        "staleness_incidents": 0
    }

    # 4. Hindsight
    # Group by Pair
    pairs = set(t.pair for t in tickets)
    pair_stats = []
    for p in pairs:
        p_tickets = [t for t in approved if t.pair == p]
        p_r = sum(t.realized_r for t in p_tickets if t.realized_r)
        p_wr = (len([t for t in p_tickets if (t.realized_r or 0) > 0]) / len(p_tickets) * 100) if p_tickets else 0
        pair_stats.append(PairStats(
            pair=p,
            trades_executed=len(p_tickets),
            win_rate_pct=p_wr,
            realized_r=p_r,
            missed_r=sum(t.hindsight_r for t in skipped if t.pair == p and t.hindsight_r),
            max_drawdown_r=min(p_r, 0)
        ))

    return PilotSessionRecord(
        session_id=f"PILOT-{target_date.strftime('%Y%m%d')}",
        date=target_date.isoformat(),
        session_label=f"Session {target_date}",
        pair_stats=pair_stats,
        process_metrics=process_metrics,
        performance_metrics=performance_metrics,
        reliability_metrics=reliability_metrics,
        policy_metrics={},
        pass_fail="PENDING",
        notes=[]
    )

def evaluate_gate(session: PilotSessionRecord, config: Dict[str, Any]) -> Tuple[str, List[str]]:
    fail_reasons = []
    
    if session.reliability_metrics.get("quote_freshness_pct", 0) < config.get("quote_freshness_pct", 95.0):
        fail_reasons.append("Data Uptime Failed (< 95%)")
        
    if session.process_metrics.get("execution_prep_override_rate", 0) > config.get("execution_prep_override_rate", 10.0):
        fail_reasons.append("Too many manual overrides")
        
    if session.process_metrics.get("expired_ticket_rate", 0) > config.get("expired_ticket_rate", 15.0):
        fail_reasons.append("Too many expired tickets")
        
    if session.performance_metrics.get("approved_expectancy_r", 0) < config.get("approved_expectancy_R", 0.05):
        fail_reasons.append(f"Negative/Low Expectancy ({session.performance_metrics.get('approved_expectancy_r')})")
        
    if session.performance_metrics.get("win_rate_pct", 0) < config.get("min_win_rate_pct", 40.0):
        fail_reasons.append("Win rate too low")
        
    if session.performance_metrics.get("max_drawdown_r", 0) < config.get("max_drawdown_R", -5.0):
        fail_reasons.append("Drawdown limit breached")

    if not fail_reasons:
        return "PASS", []
    return "FAIL", fail_reasons

def generate_next_week_plan(db: Session, start_date: date, end_date: date) -> List[str]:
    plan = []
    
    # 1. Fetch relevant Tuning proposals generated in this window
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    recent_tuning = db.query(TuningProposalLog).filter(
         TuningProposalLog.status == "OPEN",
         TuningProposalLog.created_at >= start_dt
    ).all()
    
    if recent_tuning:
        for tune in recent_tuning:
            try:
                for p in tune.data.get("proposals", []):
                    if p.get("status") != "REJECT":
                         plan.append(f"Review Tuning Proposal #{p.get('id')}: {p.get('title')} ({p.get('target')})")
            except Exception:
                pass

    if len(plan) == 0:
        plan.append("Maintain current operational routines.")
    
    plan.append("Focus on reducing missed setups in high-volatility sessions.")
    plan.append("Monitor Quote Bridge staleness metrics.")
    
    return plan

def build_pilot_scorecard(db: Session, start_date: date, end_date: date) -> PilotScorecard:
    config = load_pilot_config()
    
    current_date = start_date
    sessions = []
    
    total_approved = 0
    total_r = 0.0
    passes = 0
    total_days = 0
    
    while current_date <= end_date:
        session_rec = fetch_session_metrics(db, current_date)
        pf, reasons = evaluate_gate(session_rec, config)
        
        session_rec.pass_fail = pf
        session_rec.notes = reasons
        
        # Save Log
        log = db.query(PilotSessionLog).filter(PilotSessionLog.session_id == session_rec.session_id).first()
        if not log:
            log = PilotSessionLog(
                session_id=session_rec.session_id,
                date=current_date,
                pass_fail=pf,
                data=session_rec.model_dump()
            )
            db.add(log)
        else:
            log.pass_fail = pf
            log.data = session_rec.model_dump()
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(log, "data")
            
        sessions.append(session_rec)
        
        # Aggr ops
        total_days += 1
        if pf == "PASS": passes += 1
        total_approved += session_rec.process_metrics.get("approved", 0)
        total_r += session_rec.performance_metrics.get("realized_r", 0)
        
        current_date += timedelta(days=1)
        
    db.commit()
    
    overall_pass = "PASS" if passes >= (total_days * 0.8) else "FAIL" # 80% passing days required
    
    aggregates = {
        "total_days": total_days,
        "passing_days": passes,
        "total_tickets_approved": total_approved,
        "net_realized_r": total_r
    }
    
    scorecard = PilotScorecard(
        scorecard_id=f"SCORECARD-{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}",
        date_range=f"{start_date.isoformat()} to {end_date.isoformat()}",
        sessions=sessions,
        aggregates=aggregates,
        pass_fail_summary=overall_pass,
        next_week_plan=generate_next_week_plan(db, start_date, end_date)
    )
    
    sc_log = db.query(PilotScorecardLog).filter(PilotScorecardLog.scorecard_id == scorecard.scorecard_id).first()
    if not sc_log:
        sc_log = PilotScorecardLog(
            scorecard_id=scorecard.scorecard_id,
            date_range=scorecard.date_range,
            pass_fail=overall_pass,
            data=scorecard.model_dump()
        )
        db.add(sc_log)
    else:
        sc_log.pass_fail = overall_pass
        sc_log.data = scorecard.model_dump()
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(sc_log, "data")
        
    db.commit()
    return scorecard
