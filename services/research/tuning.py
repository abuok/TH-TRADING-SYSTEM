import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from shared.database.models import (
    OrderTicket, GuardrailsLog, ExecutionPrepLog, ManagementSuggestionLog,
    PolicySelectionLog, TuningProposalLog
)
from shared.types.tuning import Proposal, TuningProposalReport
from shared.logic.sessions import get_nairobi_time
from shared.utils.metadata import get_system_metadata

logger = logging.getLogger("TuningAssistant")

def fetch_tuning_metrics(db: Session, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
    """Gather metrics needed for generating tuning proposals."""
    
    metrics = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_tickets": db.query(OrderTicket).filter(OrderTicket.created_at.between(start_date, end_date)).count(),
        
        # Guardrails Data
        "guardrails_blocks": db.query(GuardrailsLog).filter(
            GuardrailsLog.created_at.between(start_date, end_date),
            GuardrailsLog.hard_block == True
        ).count(),
        "avg_discipline_score": db.query(func.avg(GuardrailsLog.discipline_score)).filter(
            GuardrailsLog.created_at.between(start_date, end_date)
        ).scalar() or 0.0,
        
        # Queue/Execution Data
        "total_prep_logs": db.query(ExecutionPrepLog).filter(ExecutionPrepLog.created_at.between(start_date, end_date)).count(),
        "expired_prep_logs": db.query(ExecutionPrepLog).filter(
            ExecutionPrepLog.created_at.between(start_date, end_date),
            ExecutionPrepLog.status == "EXPIRED"
        ).count(),
        
        # Trade Management
        "total_suggestions": db.query(ManagementSuggestionLog).filter(ManagementSuggestionLog.created_at.between(start_date, end_date)).count(),
        "move_sl_suggestions": db.query(ManagementSuggestionLog).filter(
            ManagementSuggestionLog.created_at.between(start_date, end_date),
            ManagementSuggestionLog.suggestion_type == "MOVE_SL_TO_BE"
        ).count(),
        
        # Policy Router
        "risk_off_policies": db.query(PolicySelectionLog).filter(
            PolicySelectionLog.created_at.between(start_date, end_date),
            PolicySelectionLog.policy_name == "RISK_OFF"
        ).count(),
        
        # Notifications (WARN/CRITICAL alerts)
        "critical_alerts": db.query(ManagementSuggestionLog).filter(
            ManagementSuggestionLog.created_at.between(start_date, end_date),
            ManagementSuggestionLog.severity == "CRITICAL"
        ).count(),
    }
    
    return metrics

def generate_proposals(metrics: Dict[str, Any]) -> List[Proposal]:
    """Generate proposals based on deterministic heuristics and gathered metrics."""
    proposals = []
    
    # 1. Guardrails Logic
    total_tickets = metrics["total_tickets"]
    if total_tickets > 0:
        block_rate = metrics["guardrails_blocks"] / total_tickets
        if block_rate > 0.4:  # If more than 40% are blocked, suggest softening
            proposals.append(Proposal(
                id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
                title="Relax Discipline Score Threshold",
                target="guardrails",
                proposed_change="Lower 'min_setup_score' from current value to allow more setups.",
                expected_impact="Increase trade frequency by reducing hard blocks.",
                confidence="MEDIUM",
                risks="May introduce lower quality setups into the execution queue.",
                rollback_plan="Revert 'min_setup_score' back in guardrails.yaml.",
                evidence_refs=[f"Block rate is unusually high at {block_rate*100:.1f}% (> 40%)."]
            ))
            
    # 2. Queue TTL Adjustments
    total_preps = metrics["total_prep_logs"]
    if total_preps > 0:
        expiry_rate = metrics["expired_prep_logs"] / total_preps
        if expiry_rate > 0.3: # If > 30% of prep tickets expire before execution
            proposals.append(Proposal(
                id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
                title="Increase Execution Prep TTL",
                target="queue",
                proposed_change="Increase `ticket_ttl_minutes` (e.g., from 60 to 120 minutes).",
                expected_impact="Reduce the rate of missed executions due to fast expirations.",
                confidence="HIGH",
                risks="Market conditions might invalidate the setup if left open for too long.",
                rollback_plan="Revert `ticket_ttl_minutes` in execution_prep config.",
                evidence_refs=[f"Very high Prep Queue expiry rate: {expiry_rate*100:.1f}%."]
            ))

    # 3. Management Rules Adjustments
    if metrics["move_sl_suggestions"] > 20: # High volume of BE moves
        proposals.append(Proposal(
            id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
            title="Aggressive Break-Even Threshold",
            target="management",
            proposed_change="Adjust MOVE_SL_TO_BE threshold down from 1.0R to 0.8R.",
            expected_impact="Lock in zero risk earlier in volatile regimes.",
            confidence="MEDIUM",
            risks="Stops might be hunted more easily before the full move completes.",
            rollback_plan="Revert management R-threshold to 1.0R.",
            evidence_refs=[f"{metrics['move_sl_suggestions']} instances of SL to BE triggered. Volatility allows earlier risk reduction."]
        ))

    # 4. Policy Router Profile
    if metrics["risk_off_policies"] > (total_tickets * 0.5):
        proposals.append(Proposal(
            id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
            title="Relax RISK_OFF Regime Strictness",
            target="policy",
            proposed_change="Decrease sensitivity of the VIX/Volatility regime check that triggers RISK_OFF.",
            expected_impact="Return to normal risk levels on more pairs instead of heavily capping R.",
            confidence="LOW",
            risks="Higher drawdowns if the macro regime remains actually hostile.",
            rollback_plan="Revert policy regime mapping to stricter thresholds.",
            evidence_refs=["RISK_OFF policy selected in > 50% of the recent window."]
        ))
        
    # 5. Notifications Alert Fatigue
    if metrics["critical_alerts"] > 50:
        proposals.append(Proposal(
            id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
            title="Adjust Critical Alert Threshold",
            target="notifications",
            proposed_change="Increase severity threshold or throttle CRITICAL alerts limit to 1 per 2 hours.",
            expected_impact="Reduce alert fatigue for operators.",
            confidence="HIGH",
            risks="Operators might miss genuinely urgent, back-to-back manual interventions.",
            rollback_plan="Revert rate limit cache timeout.",
            evidence_refs=[f"Over 50 CRITICAL alerts generated in the window ({metrics['critical_alerts']})."]
        ))

    return proposals

def generate_tuning_report(db: Session, days_back: int = 7) -> TuningProposalReport:
    """Generate the full Tuning Proposal Report artifact for a given window."""
    now_eat = get_nairobi_time()
    start_date = now_eat - timedelta(days=days_back)
    
    # 1. Gather stats
    metrics = fetch_tuning_metrics(db, start_date, now_eat)
    
    # 2. Compute dynamic proposals
    proposals = generate_proposals(metrics)
    
    # 3. Build report
    report_id = f"TUNE-{now_eat.strftime('%Y%V')}-{uuid.uuid4().hex[:4].upper()}"
    dates = f"{start_date.strftime('%Y-%m-%d')} to {now_eat.strftime('%Y-%m-%d')}"
    
    report = TuningProposalReport(
        report_id=report_id,
        created_at_eat=now_eat,
        date_range=dates,
        proposals=proposals,
        supporting_metrics=metrics,
        simulation_links=[], # Can be populated via research validates later
        reproducibility=get_system_metadata()
    )
    
    # 4. Save to DB
    log = TuningProposalLog(
        report_id=report_id,
        status="OPEN",
        data=report.model_dump(mode="json"),
        created_at=datetime.now(timezone.utc)
    )
    db.add(log)
    db.commit()
    
    logger.info(f"Generated Tuning Proposal Report: {report_id} with {len(proposals)} proposals.")
    
    return report

