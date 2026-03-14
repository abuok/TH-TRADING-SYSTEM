import os
from typing import List
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

try:
    import jinja2
except ModuleNotFoundError:
    jinja2 = None

from shared.database.models import (
    OrderTicket,
    HindsightOutcomeLog,
    AlignmentLog,
    ActionItem,
    PolicySelectionLog,
)
from shared.types.ops import WeeklyReviewReport
from shared.logic.sessions import get_nairobi_time

TEMPLATE_DIR = "services/dashboard/templates"
OUTPUT_DIR = "artifacts/ops/weekly"


class ReviewEngine:
    def __init__(self, db: Session):
        self.db = db
        self.jinja_env = None
        if jinja2 is not None:
            self.jinja_env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(TEMPLATE_DIR)
            )
            self.jinja_env.globals["url_for"] = lambda endpoint, **kwargs: (
                f"/{endpoint}/{kwargs.get('path', '')}"
            )

    def generate_weekly_report(self) -> WeeklyReviewReport:
        now = get_nairobi_time()
        start_date = now - timedelta(days=7)

        # 1. Performance
        tickets = (
            self.db.query(OrderTicket)
            .filter(OrderTicket.created_at >= start_date)
            .all()
        )
        # 1. Performance — prefer bridge-captured R over manual entries
        closed_tickets = [
            t
            for t in tickets
            if t.status in ("CLOSED", "EXECUTED", "APPROVED")
            and (t.hindsight_realized_r is not None or t.manual_outcome_r is not None)
        ]

        auto_captured = [
            t for t in closed_tickets if t.hindsight_realized_r is not None
        ]
        auto_capture_pct = (
            (len(auto_captured) / len(closed_tickets) * 100) if closed_tickets else 0.0
        )

        def get_r(ticket):
            """Return captured R first, fall back to manual."""
            if ticket.hindsight_realized_r is not None:
                return ticket.hindsight_realized_r
            return ticket.manual_outcome_r or 0.0

        def is_win(ticket):
            if ticket.hindsight_realized_r is not None:
                return ticket.hindsight_realized_r > 0
            return ticket.manual_outcome_label == "WIN"

        realized_r = sum(get_r(t) for t in closed_tickets)
        wins = len([t for t in closed_tickets if is_win(t)])

        hindsight_logs = (
            self.db.query(HindsightOutcomeLog)
            .filter(HindsightOutcomeLog.computed_at >= start_date)
            .all()
        )
        missed_r = sum(h.realized_r for h in hindsight_logs if h.realized_r > 0)

        # 2. Discipline
        blocked_setups = (
            self.db.query(AlignmentLog)
            .filter(AlignmentLog.created_at >= start_date, AlignmentLog.is_aligned.is_(False))
            .count()
        )
        avg_score = 0.0
        alignment_logs = (
            self.db.query(AlignmentLog)
            .filter(AlignmentLog.created_at >= start_date)
            .all()
        )
        if alignment_logs:
            avg_score = sum(log.alignment_score for log in alignment_logs) / len(alignment_logs)

        # 3. Decision Quality
        skipped_winners = len([h for h in hindsight_logs if h.outcome_label == "WIN"])
        skipped_losers = len([h for h in hindsight_logs if h.outcome_label == "LOSS"])
        approved_winners = wins
        approved_losers = len(
            [t for t in closed_tickets if not is_win(t) and get_r(t) < 0]
        )

        # 4. Regimes — use combined R
        approved_tickets = closed_tickets  # alias for downstream compat
        performance_by_policy = {}
        for t in closed_tickets:
            if t.active_policy_name:
                performance_by_policy[t.active_policy_name] = performance_by_policy.get(
                    t.active_policy_name, 0.0
                ) + get_r(t)

        # 5. Insights & Mistakes
        insights = [
            f"Policy Router effectively switched to RISK_OFF {self._count_switches(start_date, 'policy_risk_off')} times during high news density.",
            f"Average Guardrails score for winners: {self._avg_winner_score(start_date, hindsight_logs):.1f}",
            f"Auto-capture rate (bridge fills): {auto_capture_pct:.1f}% ({len(auto_captured)} of {len(closed_tickets)} closed trades logged automatically).",
        ]

        mistakes = []
        skip_reasons = {}
        for t in tickets:
            if t.status == "SKIPPED" and t.skip_reason:
                skip_reasons[t.skip_reason] = skip_reasons.get(t.skip_reason, 0) + 1

        top_skip = sorted(
            skip_reasons.keys(), key=lambda r: skip_reasons[r], reverse=True
        )
        if top_skip:
            mistakes.append(
                f"Most frequent skip reason: {top_skip[0]} ({skip_reasons[top_skip[0]]} times)."
            )

        # 6. Action Items Logic
        created_ais = []
        if top_skip and skip_reasons[top_skip[0]] > 5:
            ai = ActionItem(
                title=f"Review and optimize skip reason: {top_skip[0]}",
                severity="WARNING",
                source="weekly",
                evidence_links=[f"Frequency: {skip_reasons[top_skip[0]]}"],
                notes="Automatic action item created by Weekly Review Pack.",
                created_at=now,
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
                created_at=now,
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
            win_rate_pct=(wins / len(approved_tickets) * 100)
            if approved_tickets
            else 0.0,
            rule_violations_count=blocked_setups,
            avg_guardrails_score=avg_score,
            skipped_winners=skipped_winners,
            skipped_losers=skipped_losers,
            approved_winners=approved_winners,
            approved_losers=approved_losers,
            performance_by_policy=performance_by_policy,
            top_insights=insights,
            top_mistakes=mistakes,
            created_action_items=created_ais,
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
        return (
            self.db.query(PolicySelectionLog)
            .filter(
                PolicySelectionLog.created_at >= start,
                PolicySelectionLog.policy_name == policy_name,
            )
            .count()
        )

    def _avg_winner_score(self, start, hindsight_logs: List[HindsightOutcomeLog]):
        # Get ticket_ids of winners from hindsight logs
        winning_ticket_ids = [
            h.ticket_id for h in hindsight_logs if h.outcome_label == "WIN"
        ]
        if not winning_ticket_ids:
            return 0.0

        # Get setup_packet_ids for those tickets
        setup_ids = (
            self.db.query(OrderTicket.setup_packet_id)
            .filter(OrderTicket.ticket_id.in_(winning_ticket_ids))
            .all()
        )
        setup_ids = [s[0] for s in setup_ids if s[0]]

        if not setup_ids:
            return 0.0

        # Get avg score from guardrails logs for those setups
        avg_discipline = (
            self.db.query(func.avg(AlignmentLog.alignment_score))
            .filter(AlignmentLog.setup_packet_id.in_(setup_ids))
            .scalar()
        )

        return float(avg_discipline) if avg_discipline else 0.0
