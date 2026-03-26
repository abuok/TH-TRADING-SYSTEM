import os
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    import jinja2
except ModuleNotFoundError:
    jinja2 = None

from shared.database.models import (
    HindsightOutcomeLog,
    IncidentLog,
    OrderTicket,
    Packet,
    PolicySelectionLog,
)
from shared.logic.sessions import get_nairobi_time
from shared.types.ops import DailyOpsReport, HindsightSummary

TEMPLATE_DIR = "services/dashboard/templates"
OUTPUT_DIR = "artifacts/ops/daily"


class OpsEngine:
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

    def generate_daily_report(self) -> DailyOpsReport:
        now = get_nairobi_time()
        yesterday = now - timedelta(days=1)

        # 1. Health & Incidents
        incidents = (
            self.db.query(IncidentLog).filter(IncidentLog.created_at >= yesterday).all()
        )
        health_status = "STABLE"
        if any(i.severity in ["ERROR", "CRITICAL"] for i in incidents):
            health_status = "DEGRADED"

        # 2. Policies
        latest_policies = {}  # pair -> policy
        # Get latest policy per pair
        subquery = (
            self.db.query(
                PolicySelectionLog.pair,
                func.max(PolicySelectionLog.created_at).label("max_ts"),
            )
            .group_by(PolicySelectionLog.pair)
            .subquery()
        )

        current_policies = (
            self.db.query(PolicySelectionLog)
            .join(
                subquery,
                (PolicySelectionLog.pair == subquery.c.pair)
                & (PolicySelectionLog.created_at == subquery.c.max_ts),
            )
            .all()
        )
        for p in current_policies:
            latest_policies[p.pair] = p.policy_name

        switches_24h = (
            self.db.query(PolicySelectionLog)
            .filter(PolicySelectionLog.created_at >= yesterday)
            .count()
        )

        # 3. Queue Stats
        tickets = (
            self.db.query(OrderTicket).filter(OrderTicket.created_at >= yesterday).all()
        )
        approvals = len([t for t in tickets if t.status == "APPROVED"])
        skips = len([t for t in tickets if t.status == "SKIPPED"])
        expires = len([t for t in tickets if t.status == "EXPIRED"])

        skip_reasons = {}
        for t in tickets:
            if t.status == "SKIPPED" and t.skip_reason:
                skip_reasons[t.skip_reason] = skip_reasons.get(t.skip_reason, 0) + 1

        top_skips = sorted(
            skip_reasons.keys(), key=lambda r: skip_reasons[r], reverse=True
        )[:5]

        # 4. Hindsight
        hindsight_logs = (
            self.db.query(HindsightOutcomeLog)
            .filter(HindsightOutcomeLog.computed_at >= yesterday)
            .all()
        )
        missed_r = sum(h.realized_r for h in hindsight_logs if h.realized_r > 0)
        winners = len([h for h in hindsight_logs if h.outcome_label == "WIN"])

        h_summary = HindsightSummary(
            total_skipped=skips,
            total_expired=expires,
            avg_missed_r=missed_r / len(hindsight_logs) if hindsight_logs else 0.0,
            missed_winners_count=winners,
        )

        # 5. Checklist (Dynamic logic based on current state)
        checklist_do, checklist_dont = self._generate_dynamic_checklist(health_status)

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
            checklist_dont=checklist_dont,
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
        if self.jinja_env is not None:
            # The base.html template expects a FastAPI request object for sidebar highlighting
            class MockRequest:
                class URL:
                    path = "/dashboard/ops-daily"
                url = URL()
            
            template = self.jinja_env.get_template("ops_daily_template.html")
            return template.render(report=report, request=MockRequest())

        return (
            f"<html><body><h1>Daily Ops Report</h1>"
            f"<p>ID: {report.report_id}</p>"
            f"<p>Health: {report.health_status}</p>"
            f"<p>Skips: {report.queue_skips}</p>"
            f"</body></html>"
        )

    def _generate_dynamic_checklist(self, health_status: str):
        do_items = [
            "Review Manual Review Queue every 4 hours.",
            "Ensure hindsight scoring is running for all skipped trades.",
        ]
        dont_items = []

        if health_status != "STABLE":
            dont_items.append(
                f"Ignore system health warnings (currently {health_status})."
            )

        # Check for upcoming news in next 8 hours
        now = get_nairobi_time()
        later = now + timedelta(hours=8)

        context = (
            self.db.query(Packet)
            .filter(Packet.packet_type == "MarketContextPacket")
            .order_by(Packet.created_at.desc())
            .first()
        )
        if context and "high_impact_events" in context.data:
            upcoming = []
            for ev in context.data["high_impact_events"]:
                try:
                    ev_time = datetime.fromisoformat(ev["time"].replace("Z", "+00:00"))
                    if now <= ev_time <= later:
                        upcoming.append(ev["event"])
                except (ValueError, TypeError, KeyError):
                    continue

            if upcoming:
                dont_items.append(
                    f"Trade during upcoming high-impact news: {', '.join(upcoming[:2])}"
                )
                do_items.append("Tighten stop losses before news events.")
            else:
                do_items.append(
                    "Standard execution rules apply (no imminent high-impact news)."
                )

        if not dont_items:
            dont_items.append("Over-leverage during high volatility session openings.")

        return do_items, dont_items
