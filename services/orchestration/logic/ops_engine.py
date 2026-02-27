import os
import uuid
from datetime import datetime, timedelta
import jinja2
from sqlalchemy.orm import Session
from sqlalchemy import func

from shared.database.models import IncidentLog, OrderTicket, PolicySelectionLog, HindsightOutcomeLog, GuardrailsLog
from shared.types.ops import DailyOpsReport, HindsightSummary
from shared.logic.sessions import get_nairobi_time

TEMPLATE_DIR = "services/dashboard/templates"
OUTPUT_DIR = "artifacts/ops/daily"

class OpsEngine:
    def __init__(self, db: Session):
        self.db = db
        self.jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR))

    def generate_daily_report(self) -> DailyOpsReport:
        now = get_nairobi_time()
        yesterday = now - timedelta(days=1)
        
        # 1. Health & Incidents
        incidents = self.db.query(IncidentLog).filter(IncidentLog.created_at >= yesterday).all()
        health_status = "STABLE"
        if any(i.severity in ["ERROR", "CRITICAL"] for i in incidents):
            health_status = "DEGRADED"
        
        # 2. Policies
        latest_policies = {} # pair -> policy
        # Get latest policy per pair
        subquery = self.db.query(
            PolicySelectionLog.pair,
            func.max(PolicySelectionLog.timestamp).label("max_ts")
        ).group_by(PolicySelectionLog.pair).subquery()
        
        current_policies = self.db.query(PolicySelectionLog).join(
            subquery,
            (PolicySelectionLog.pair == subquery.c.pair) & (PolicySelectionLog.timestamp == subquery.c.max_ts)
        ).all()
        for p in current_policies:
            latest_policies[p.pair] = p.policy_name
            
        switches_24h = self.db.query(PolicySelectionLog).filter(PolicySelectionLog.timestamp >= yesterday).count()
        
        # 3. Queue Stats
        tickets = self.db.query(OrderTicket).filter(OrderTicket.created_at >= yesterday).all()
        approvals = len([t for t in tickets if t.status == "APPROVED"])
        skips = len([t for t in tickets if t.status == "SKIPPED"])
        expires = len([t for t in tickets if t.status == "EXPIRED"])
        
        skip_reasons = {}
        for t in tickets:
            if t.status == "SKIPPED" and t.skip_reason:
                skip_reasons[t.skip_reason] = skip_reasons.get(t.skip_reason, 0) + 1
        
        top_skips = sorted(skip_reasons.keys(), key=lambda r: skip_reasons[r], reverse=True)[:5]
        
        # 4. Hindsight
        hindsight_logs = self.db.query(HindsightOutcomeLog).filter(HindsightOutcomeLog.computed_at >= yesterday).all()
        missed_r = sum(h.realized_r for h in hindsight_logs if h.realized_r > 0)
        winners = len([h for h in hindsight_logs if h.outcome_label == "WIN"])
        
        h_summary = HindsightSummary(
            total_skipped=skips,
            total_expired=expires,
            avg_missed_r=missed_r / len(hindsight_logs) if hindsight_logs else 0.0,
            missed_winners_count=winners
        )
        
        # 5. Checklist (Dynamic logic based on current state)
        checklist_do = [
            "Monitor news for high-impact red events.",
            "Review Manual Review Queue every 4 hours.",
            "Ensure hindsight scoring is running for all skipped trades."
        ]
        checklist_dont = [
            "Over-leverage during high volatility session openings.",
            "Ignore system health warnings (currently " + health_status + ")."
        ]
        
        report = DailyOpsReport(
            report_id=f"ops_{now.strftime('%Y%m%d')}",
            timestamp=now,
            health_status=health_status,
            incident_count=len(incidents),
            active_policies=latest_policies,
            policy_switches_24h=switches_24h,
            queue_approvals=approvals,
            queue_skips=skips,
            queue_expires=expires,
            top_skip_reasons=top_skips,
            hindsight_yesterday=h_summary,
            checklist_do=checklist_do,
            checklist_dont=checklist_dont
        )
        
        # Render HTML
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        html_content = self.render_html(report)
        html_filename = f"{report.report_id}.html"
        html_path = os.path.join(OUTPUT_DIR, html_filename)
        
        with open(html_path, "w") as f:
            f.write(html_content)
            
        return report, html_path

    def render_html(self, report: DailyOpsReport) -> str:
        template = self.jinja_env.get_template("ops_daily_template.html")
        return template.render(report=report)
