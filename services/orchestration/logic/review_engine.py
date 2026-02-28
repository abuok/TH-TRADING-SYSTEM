import os
import uuid
import json
from typing import List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

try:
    import jinja2
except ModuleNotFoundError:
    jinja2 = None

from shared.database.models import OrderTicket, HindsightOutcomeLog, GuardrailsLog, ActionItem, PolicySelectionLog
from shared.types.ops import WeeklyReviewReport
from shared.logic.sessions import get_nairobi_time

TEMPLATE_DIR = "services/dashboard/templates"
OUTPUT_DIR = "artifacts/ops/weekly"

class ReviewEngine:
    def __init__(self, db: Session):
        self.db = db
        self.jinja_env = None
        if jinja2 is not None:
            self.jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR))

    def generate_weekly_report(self) -> WeeklyReviewReport:
        now = get_nairobi_time()
        start_date = now - timedelta(days=7)
        
        # 1. Performance
        tickets = self.db.query(OrderTicket).filter(OrderTicket.created_at >= start_date).all()
        approved_tickets = [t for t in tickets if t.status == "APPROVED"]
        
        realized_r = sum(t.manual_outcome_r for t in approved_tickets if t.manual_outcome_r is not None)
        wins = len([t for t in approved_tickets if t.manual_outcome_label == "WIN"])
        
        hindsight_logs = self.db.query(HindsightOutcomeLog).filter(HindsightOutcomeLog.computed_at >= start_date).all()
        missed_r = sum(h.realized_r for h in hindsight_logs if h.realized_r > 0)
        
        # 2. Discipline
        violations = self.db.query(GuardrailsLog).filter(
            GuardrailsLog.created_at >= start_date,
            GuardrailsLog.hard_block == True
        ).count()
        
        avg_score = 0.0
        gr_logs = self.db.query(GuardrailsLog).filter(GuardrailsLog.created_at >= start_date).all()
        if gr_logs:
            avg_score = sum(l.discipline_score for l in gr_logs) / len(gr_logs)
        
        # 3. Decision Quality
        skipped_winners = len([h for h in hindsight_logs if h.outcome_label == "WIN"])
        skipped_losers = len([h for h in hindsight_logs if h.outcome_label == "LOSS"])
        approved_winners = wins
        approved_losers = len([t for t in approved_tickets if t.manual_outcome_label == "LOSS"])
        
        # 4. Regimes
        performance_by_policy = {}
        for t in approved_tickets:
            if t.active_policy_name:
                performance_by_policy[t.active_policy_name] = performance_by_policy.get(t.active_policy_name, 0.0) + (t.manual_outcome_r or 0.0)
        
        # 5. Insights & Mistakes
        insights = [
            f"Policy Router effectively switched to RISK_OFF {self._count_switches(start_date, 'policy_risk_off')} times during high news density.",
            f"Average Guardrails score for winners: {self._avg_winner_score(start_date, hindsight_logs):.1f}"
        ]
        
        mistakes = []
        skip_reasons = {}
        for t in tickets:
            if t.status == "SKIPPED" and t.skip_reason:
                skip_reasons[t.skip_reason] = skip_reasons.get(t.skip_reason, 0) + 1
        
        top_skip = sorted(skip_reasons.keys(), key=lambda r: skip_reasons[r], reverse=True)
        if top_skip:
            mistakes.append(f"Most frequent skip reason: {top_skip[0]} ({skip_reasons[top_skip[0]]} times).")
        
        # 6. Action Items Logic
        created_ais = []
        if top_skip and skip_reasons[top_skip[0]] > 5:
            ai = ActionItem(
                title=f"Review and optimize skip reason: {top_skip[0]}",
                severity="WARNING",
                source="weekly",
                evidence_links=[f"Frequency: {skip_reasons[top_skip[0]]}"],
                notes="Automatic action item created by Weekly Review Pack.",
                created_at=now
            )
            self.db.add(ai)
            created_ais.append(ai.title)
            
        if missed_r > 5.0:
            ai = ActionItem(
                title="Investigate high missed opportunity (Hindsight)",
                severity="ERROR",
                source="weekly",
                evidence_links=[f"Missed R: {missed_r:.2f}"],
                notes="Significant profit left on the table. Review guardrails thresholds.",
                created_at=now
            )
            self.db.add(ai)
            created_ais.append(ai.title)
        
        self.db.commit()
        
        report = WeeklyReviewReport(
            report_id=f"weekly_{now.strftime('%Y%V')}",
            start_date=start_date,
            end_date=now,
            total_realized_r=realized_r,
            total_missed_r=missed_r,
            win_rate_pct=(wins / len(approved_tickets) * 100) if approved_tickets else 0.0,
            rule_violations_count=violations,
            avg_guardrails_score=avg_score,
            skipped_winners=skipped_winners,
            skipped_losers=skipped_losers,
            approved_winners=approved_winners,
            approved_losers=approved_losers,
            performance_by_policy=performance_by_policy,
            top_insights=insights,
            top_mistakes=mistakes,
            created_action_items=created_ais
        )
        
        # Render HTML & Save JSON
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        html_content = self.render_html(report)
        html_path = os.path.join(OUTPUT_DIR, f"{report.report_id}.html")
        json_path = os.path.join(OUTPUT_DIR, f"{report.report_id}.json")
        
        with open(html_path, "w") as f:
            f.write(html_content)
        with open(json_path, "w") as f:
            f.write(report.model_dump_json())
            
        return report, html_path

    def render_html(self, report: WeeklyReviewReport) -> str:
        if self.jinja_env is not None:
            template = self.jinja_env.get_template("ops_weekly_template.html")
            return template.render(report=report)

        return (
            f"<html><body><h1>Weekly Review Report</h1>"
            f"<p>ID: {report.report_id}</p>"
            f"<p>Realized R: {report.total_realized_r}</p>"
            f"<p>Missed R: {report.total_missed_r}</p>"
            f"</body></html>"
        )

    def _count_switches(self, start, policy_name):
        return self.db.query(PolicySelectionLog).filter(
            PolicySelectionLog.created_at >= start,
            PolicySelectionLog.policy_name == policy_name
        ).count()

    def _avg_winner_score(self, start, hindsight_logs: List[HindsightOutcomeLog]):
        # Get ticket_ids of winners from hindsight logs
        winning_ticket_ids = [h.ticket_id for h in hindsight_logs if h.outcome_label == "WIN"]
        if not winning_ticket_ids:
            return 0.0
            
        # Get setup_packet_ids for those tickets
        setup_ids = self.db.query(OrderTicket.setup_packet_id).filter(
            OrderTicket.ticket_id.in_(winning_ticket_ids)
        ).all()
        setup_ids = [s[0] for s in setup_ids if s[0]]
        
        if not setup_ids:
            return 0.0

        # Get avg score from guardrails logs for those setups
        res = self.db.query(func.avg(GuardrailsLog.discipline_score)).filter(
            GuardrailsLog.setup_packet_id.in_(setup_ids)
        ).scalar()
        
        return float(res) if res else 0.0
