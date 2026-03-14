"""
shared/logic/briefing.py
Session Briefing Pack assembly, HTML rendering, and artifact persistence.
All times use Africa/Nairobi (UTC+3).
"""

import logging
import os
import uuid
from datetime import datetime, timezone

import pytz
from sqlalchemy.orm import Session

from shared.database.models import (
    IncidentLog,
    KillSwitch,
    OrderTicket,
    Packet,
    SessionBriefing,
)
from shared.logic.sessions import get_session_label
from shared.types.briefing import (
    BriefingPack,
    DeltaSection,
    MarketContextSummary,
    OperatorAction,
    PairOverview,
    RiskBudget,
    SetupSummary,
    StaleWarning,
    SystemStatus,
    TicketSummary,
    nairobi_now,
)

logger = logging.getLogger("BriefingPack")
NAIROBI = pytz.timezone("Africa/Nairobi")

TRACKED_PAIRS = ["XAUUSD", "GBPJPY"]

# TTLs (seconds)
TTL_CONTEXT = 30 * 60  # 30 min
TTL_SETUP = 2 * 60 * 60  # 2 h
TTL_RISK = 60 * 60  # 1 h

# Default risk budget (read from env or use defaults)
DEFAULT_RISK_BUDGET = RiskBudget(
    max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "2.0")),
    max_total_loss_pct=float(os.getenv("MAX_TOTAL_LOSS_PCT", "5.0")),
    max_consecutive_losses=int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3")),
    allowed_sessions=["LONDON", "NEW YORK"],
    risk_per_trade_usd=float(os.getenv("RISK_PER_TRADE_USD", "100.0")),
)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _is_stale(created_at: datetime, ttl: int) -> bool:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created_at).total_seconds() > ttl


def _age_str(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - created_at
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        return f"{mins}m ago"
    return f"{mins // 60}h {mins % 60}m ago"


# ──────────────────────────────────────────────────────────────────────────
# Section assemblers
# ──────────────────────────────────────────────────────────────────────────


def _build_system_status(db: Session) -> SystemStatus:
    """Collect kill switches and last incident."""
    active_ks = db.query(KillSwitch).filter(KillSwitch.is_active == 1).all()
    ks_labels = []
    for k in active_ks:
        label = k.switch_type
        if k.target:
            label += f":{k.target}"
        ks_labels.append(label)

    last_incident = (
        db.query(IncidentLog).order_by(IncidentLog.created_at.desc()).first()
    )

    return SystemStatus(
        healthy_services=[],  # will be filled async; left empty for sync path
        unhealthy_services=[],
        active_kill_switches=ks_labels,
        last_incident_summary=last_incident.message if last_incident else None,
        last_incident_severity=last_incident.severity if last_incident else None,
    )


def _build_market_context(db: Session) -> MarketContextSummary:
    """Pull latest MarketContextPacket and extract events/windows."""
    packet = (
        db.query(Packet)
        .filter(Packet.packet_type == "MarketContextPacket")
        .order_by(Packet.created_at.desc())
        .first()
    )

    if not packet:
        return MarketContextSummary(is_stale=True)

    stale = _is_stale(packet.created_at, TTL_CONTEXT)
    data = packet.data or {}
    return MarketContextSummary(
        high_impact_events=data.get("high_impact_events", [])[:5],
        no_trade_windows=data.get("no_trade_windows", []),
        proxy_snapshots=data.get("proxies", {}),
        is_stale=stale,
    )


def _build_pair_overview(pair: str, db: Session) -> PairOverview:
    """Build per-pair overview: bias, levels, setups, latest ticket."""
    warnings: list[StaleWarning] = []
    has_stale = False

    # ── Bias (from Fundamentals) ──────────────────────────────────────
    bias_packet = (
        db.query(Packet)
        .filter(
            Packet.packet_type == "PairFundamentalsPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
        .order_by(Packet.created_at.desc())
        .first()
    )

    bias, bias_score, inval, drvs = "unknown", None, "N/A", []
    if bias_packet:
        d = bias_packet.data
        score = d.get("bias_score", 0)
        bias_score = score
        bias = d.get("bias_label", "unknown")
        inval = d.get("invalidation_criteria", "N/A")
        drvs = d.get("drivers", [])

        if _is_stale(bias_packet.created_at, TTL_RISK):
            has_stale = True
            warnings.append(
                StaleWarning(
                    field="bias",
                    reason=f"PairFundamentalsPacket is older than {TTL_RISK // 3600}h",
                )
            )
    else:
        warnings.append(
            StaleWarning(field="bias", reason="No PairFundamentalsPacket found")
        )

    # ── Key levels (from latest market context or setup levels) ───────
    key_levels: dict[str, float] = {}
    ctx_packet = (
        db.query(Packet)
        .filter(
            Packet.packet_type == "MarketContextPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
        .order_by(Packet.created_at.desc())
        .first()
    )
    if ctx_packet:
        metrics = ctx_packet.data.get("metrics", {})
        for k in (
            "asia_high",
            "asia_low",
            "london_high",
            "london_low",
            "prior_day_high",
            "prior_day_low",
            "london_open",
        ):
            if k in metrics:
                key_levels[k] = metrics[k]

    # ── Setups ────────────────────────────────────────────────────────
    setup_packets = (
        db.query(Packet)
        .filter(
            Packet.packet_type == "TechnicalSetupPacket",
            Packet.data["asset_pair"].as_string() == pair,
        )
        .order_by(Packet.created_at.desc())
        .limit(20)
        .all()
    )

    stage_counts: dict[str, int] = {}
    top_setups: list[SetupSummary] = []
    for sp in setup_packets:
        stage = sp.data.get("stage", sp.data.get("strategy_name", "UNKNOWN"))
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        if len(top_setups) < 3:
            top_setups.append(
                SetupSummary(
                    stage=stage,
                    score=sp.data.get("score"),
                    asset_pair=pair,
                    created_at=sp.created_at,
                )
            )

    if not setup_packets:
        warnings.append(
            StaleWarning(field="setups", reason="No TechnicalSetupPacket found")
        )

    # ── Latest ticket ─────────────────────────────────────────────────
    ticket = (
        db.query(OrderTicket)
        .filter(OrderTicket.pair == pair)
        .order_by(OrderTicket.created_at.desc())
        .first()
    )

    latest_ticket = None
    if ticket:
        latest_ticket = TicketSummary(
            ticket_id=ticket.ticket_id,
            status=ticket.status,
            direction=ticket.direction,
            entry_price=ticket.entry_price,
            lot_size=ticket.lot_size,
            rr_tp1=ticket.rr_tp1,
            top_reason=ticket.block_reason if ticket.status == "BLOCKED" else None,
        )
    else:
        warnings.append(StaleWarning(field="ticket", reason="No OrderTicket found"))

    return PairOverview(
        pair=pair,
        bias=bias,
        bias_score=bias_score,
        key_levels=key_levels,
        setup_count_by_stage=stage_counts,
        top_setups=top_setups,
        latest_ticket=latest_ticket,
        has_stale_data=has_stale,
        stale_warnings=warnings,
        bias_drivers=drvs,
        bias_invalidation=inval,
    )


def _build_operator_actions(
    system: SystemStatus,
    market: MarketContextSummary,
    pairs: list[PairOverview],
) -> list[OperatorAction]:
    actions: list[OperatorAction] = []

    if system.active_kill_switches:
        actions.append(
            OperatorAction(
                priority="HIGH",
                category="CHECK",
                description=f"Kill switches active: {', '.join(system.active_kill_switches)}. Verify intent before trading.",
            )
        )

    if market.no_trade_windows:
        windows_str = "; ".join(
            str(w.get("label", w)) for w in market.no_trade_windows[:3]
        )
        actions.append(
            OperatorAction(
                priority="HIGH",
                category="AVOID",
                description=f"No-trade windows today: {windows_str}. Do NOT enter during these periods.",
            )
        )

    if market.is_stale:
        actions.append(
            OperatorAction(
                priority="HIGH",
                category="CHECK",
                description="MarketContextPacket is STALE. Refresh economic calendar before taking any trade.",
            )
        )

    for p in pairs:
        if p.has_stale_data:
            actions.append(
                OperatorAction(
                    priority="MEDIUM",
                    category="MONITOR",
                    description=f"{p.pair}: Some data is stale ({', '.join(w.field for w in p.stale_warnings)}). Treat setups with caution.",
                )
            )
        if p.latest_ticket and p.latest_ticket.status == "BLOCKED":
            actions.append(
                OperatorAction(
                    priority="HIGH",
                    category="AVOID",
                    description=f"{p.pair}: Latest ticket is BLOCKED — {p.latest_ticket.top_reason or 'Risk engine rejection'}. Do not force entry.",
                )
            )
        if p.bias == "unknown":
            actions.append(
                OperatorAction(
                    priority="LOW",
                    category="MONITOR",
                    description=f"{p.pair}: Bias is unknown. Wait for bias confirmation before committing to a direction.",
                )
            )
        if p.latest_ticket and p.latest_ticket.status == "PENDING":
            actions.append(
                OperatorAction(
                    priority="MEDIUM",
                    category="EXECUTE",
                    description=f"{p.pair}: Active PENDING ticket ({p.latest_ticket.ticket_id}) awaiting operator review.",
                )
            )

    if not actions:
        actions.append(
            OperatorAction(
                priority="LOW",
                category="MONITOR",
                description="System nominal. Monitor for setups during the active session window.",
            )
        )

    return actions


def _build_delta(
    db: Session, now_nairobi: datetime, session_label: str
) -> DeltaSection | None:
    """Compare with the most recent previous briefing for the same session."""
    today = now_nairobi.date()
    prev = (
        db.query(SessionBriefing)
        .filter(
            SessionBriefing.session_label == session_label,
            SessionBriefing.date == today,
        )
        .order_by(SessionBriefing.created_at.desc())
        .first()
    )

    if not prev:
        return DeltaSection(summary="First briefing for this session today.")

    prev_data = prev.data or {}
    prev_tickets: set = set()
    for po in prev_data.get("pair_overviews", []):
        t = po.get("latest_ticket")
        if t:
            prev_tickets.add(t.get("ticket_id", ""))

    # Current tickets
    cur_tickets: set = set()
    all_tickets = (
        db.query(OrderTicket).order_by(OrderTicket.created_at.desc()).limit(20).all()
    )
    for t in all_tickets:
        cur_tickets.add(t.ticket_id)

    new_tkt = list(cur_tickets - prev_tickets)

    # Incident delta
    prev_ts = prev.created_at
    if prev_ts.tzinfo is None:
        prev_ts = prev_ts.replace(tzinfo=timezone.utc)
    new_incidents = (
        db.query(IncidentLog).filter(IncidentLog.created_at > prev_ts).count()
    )

    summary_parts = []
    if new_tkt:
        summary_parts.append(f"{len(new_tkt)} new ticket(s)")
    if new_incidents:
        summary_parts.append(f"{new_incidents} new incident(s)")
    summary = f"Delta since {_age_str(prev.created_at)}: " + (
        ", ".join(summary_parts) or "no significant changes"
    )

    return DeltaSection(
        previous_briefing_id=prev.briefing_id,
        new_tickets=new_tkt,
        incident_count_delta=new_incidents,
        summary=summary,
    )


# ──────────────────────────────────────────────────────────────────────────
# Main assembler
# ──────────────────────────────────────────────────────────────────────────


def assemble_briefing(
    db: Session,
    now_nairobi: datetime | None = None,
    is_delta: bool = False,
) -> BriefingPack:
    """
    Assemble a BriefingPack from current DB state.
    Uses Africa/Nairobi time; marks stale inputs with warnings.
    """
    if now_nairobi is None:
        now_nairobi = nairobi_now()

    session_label = get_session_label(now_nairobi)
    briefing_id = f"BRIEF-{session_label[:2]}-{now_nairobi.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    # Gather sections
    system = _build_system_status(db)
    market = _build_market_context(db)
    pairs = [_build_pair_overview(p, db) for p in TRACKED_PAIRS]
    actions = _build_operator_actions(system, market, pairs)
    delta = _build_delta(db, now_nairobi, session_label) if is_delta else None

    # Global warnings
    global_warnings: list[str] = []
    if system.active_kill_switches:
        global_warnings.append(
            f"⚠ KILL SWITCHES ACTIVE: {', '.join(system.active_kill_switches)}"
        )
    if market.is_stale:
        global_warnings.append(
            "⚠ Market context data is STALE — calendar inputs unreliable"
        )
    for p in pairs:
        if p.has_stale_data:
            global_warnings.append(f"⚠ {p.pair}: stale data detected")

    return BriefingPack(
        briefing_id=briefing_id,
        created_at=now_nairobi,
        session_label=session_label,
        date=now_nairobi.date(),
        is_delta=is_delta,
        system_status=system,
        market_context=market,
        pair_overviews=pairs,
        risk_budget=DEFAULT_RISK_BUDGET,
        operator_actions=actions,
        delta_from_previous=delta,
        global_warnings=global_warnings,
    )


# ──────────────────────────────────────────────────────────────────────────
# HTML renderer
# ──────────────────────────────────────────────────────────────────────────


def render_briefing_html(pack: BriefingPack) -> str:
    """Produce a print-ready HTML page for the briefing pack."""

    def badge(text: str, colour: str) -> str:
        return f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:700;">{text}</span>'

    def section(title: str, content: str, bg: str = "#1e2433") -> str:
        return f"""
        <div style="background:{bg};border-radius:12px;padding:1.5rem;margin-bottom:1.5rem;">
          <h2 style="color:#94a3b8;font-size:0.85rem;text-transform:uppercase;letter-spacing:2px;margin:0 0 1rem;">{title}</h2>
          {content}
        </div>"""

    # ── Header
    type_badge = (
        badge("INTRADAY DELTA", "#7c3aed")
        if pack.is_delta
        else badge("PRE-SESSION", "#0ea5e9")
    )
    session_color = {"LONDON": "#10b981", "NEW YORK": "#f59e0b", "ASIA": "#6366f1"}.get(
        pack.session_label, "#64748b"
    )

    warnings_html = ""
    if pack.global_warnings:
        items = "\n".join(
            f'<li style="color:#ef4444;margin:0.25rem 0;">{w}</li>'
            for w in pack.global_warnings
        )
        warnings_html = f"""
        <div style="background:#1a0a0a;border:1px solid #ef4444;border-radius:8px;padding:1rem;margin-bottom:1.5rem;">
          <strong style="color:#ef4444;">⚠ Global Warnings</strong>
          <ul style="margin:0.5rem 0 0;padding-left:1.2rem;">{items}</ul>
        </div>"""

    # ── System Status
    ks = pack.system_status.active_kill_switches
    ks_html = (
        " ".join(badge(k, "#ef4444") for k in ks)
        if ks
        else '<span style="color:#10b981;">None active ✓</span>'
    )
    last_inc = pack.system_status.last_incident_summary or "No recent incidents"
    inc_sev = pack.system_status.last_incident_severity or "INFO"
    inc_col = {"CRITICAL": "#ef4444", "ERROR": "#f97316", "WARNING": "#f59e0b"}.get(
        inc_sev, "#94a3b8"
    )
    sys_html = f"""
      <p style="margin:0.25rem 0;"><strong>Kill Switches:</strong> {ks_html}</p>
      <p style="margin:0.25rem 0;"><strong>Last Incident:</strong>
        <span style="color:{inc_col};">[{inc_sev}]</span> {last_inc}</p>"""
    sys_section = section("🔧 System Status", sys_html)

    # ── Market Context
    ev_rows = ""
    for ev in pack.market_context.high_impact_events:
        ev_rows += f"<tr><td>{ev.get('time', '')}</td><td>{ev.get('currency', '')}</td><td>{ev.get('event', '')}</td></tr>"
    if not ev_rows:
        ev_rows = '<tr><td colspan="3" style="color:#64748b;">No high-impact events found</td></tr>'

    ntw_items = ""
    for w in pack.market_context.no_trade_windows:
        ntw_items += f"<li>{w.get('label', str(w))}</li>"
    ntw_html = (
        f"<ul style='margin:0;padding-left:1.2rem;'>{ntw_items}</ul>"
        if ntw_items
        else '<span style="color:#10b981;">No restricted windows</span>'
    )

    stale_badge = (
        badge("STALE", "#ef4444")
        if pack.market_context.is_stale
        else badge("FRESH", "#10b981")
    )
    mkt_html = f"""
      <p style="margin:0 0 0.5rem;">{stale_badge}</p>
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-bottom:1rem;">
        <thead><tr style="color:#64748b;"><th style="text-align:left;">Time</th><th>CCY</th><th>Event</th></tr></thead>
        <tbody>{ev_rows}</tbody>
      </table>
      <strong>No-Trade Windows:</strong> {ntw_html}"""
    mkt_section = section("📅 Market Context", mkt_html)

    # ── Pair Overviews
    pair_html = ""
    for po in pack.pair_overviews:
        bias_col = {
            "BULLISH": "#10b981",
            "BEARISH": "#ef4444",
            "NEUTRAL": "#f59e0b",
        }.get(po.bias, "#64748b")
        ticket_html = ""
        if po.latest_ticket:
            t = po.latest_ticket
            t_col = {
                "BLOCKED": "#ef4444",
                "PENDING": "#f59e0b",
                "TAKEN": "#10b981",
            }.get(t.status, "#94a3b8")
            ticket_html = f"""<p style="margin:0.5rem 0;">
              <strong>Latest Ticket:</strong> {badge(t.status, t_col)} {t.direction} @ {t.entry_price:.5f}
              | Lots: {t.lot_size} | RR: {t.rr_tp1:.1f}R
              {f'<br><em style="color:#ef4444;">Block reason: {t.top_reason}</em>' if t.top_reason else ""}</p>"""
        else:
            ticket_html = (
                "<p style='color:#64748b;margin:0.5rem 0;'>No ticket generated</p>"
            )

        levels_html = ""
        if po.key_levels:
            levels_html = (
                "<div style='display:flex;flex-wrap:wrap;gap:0.5rem;margin:0.5rem 0;'>"
            )
            for k, v in po.key_levels.items():
                levels_html += f'<span style="background:#0f172a;border:1px solid #334155;border-radius:6px;padding:2px 8px;font-size:0.8rem;">{k.replace("_", " ").title()}: <strong>{v:.5f}</strong></span>'
            levels_html += "</div>"

        top_setups_html = ""
        for s in po.top_setups[:3]:
            score_str = f" | Score: {s.score:.0f}" if s.score is not None else ""
            top_setups_html += f"<li>{s.stage}{score_str}</li>"

        warn_html = ""
        if po.stale_warnings:
            warn_items = "".join(
                f"<li style='color:#f97316;'>{w.field}: {w.reason}</li>"
                for w in po.stale_warnings
            )
            warn_html = f"<ul style='margin:0.25rem 0;padding-left:1.2rem;font-size:0.8rem;'>{warn_items}</ul>"

        pair_html += f"""
        <div style="border:1px solid #334155;border-radius:10px;padding:1rem;margin-bottom:1rem;">
          <h3 style="margin:0 0 0.5rem;display:flex;align-items:center;gap:0.5rem;">
            {po.pair} <span style="color:{bias_col};font-size:0.85rem;">{po.bias}</span>
          </h3>
          {levels_html}
          <p style="margin:0.25rem 0;font-size:0.85rem;"><strong>Setups:</strong>
            {", ".join(f"{k}×{v}" for k, v in po.setup_count_by_stage.items()) or "None"}
          </p>
          {"<ul style='font-size:0.85rem;margin:0.25rem 0;padding-left:1.2rem;'>" + top_setups_html + "</ul>" if top_setups_html else ""}
          {ticket_html}
          {warn_html}
        </div>"""
    pairs_section = section("📊 Pair Overviews", pair_html)

    # ── Risk Budget
    rb = pack.risk_budget
    rb_html = f"""
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;font-size:0.85rem;">
        <div><strong>Max Daily Loss</strong><br>{rb.max_daily_loss_pct}%</div>
        <div><strong>Max Total Loss</strong><br>{rb.max_total_loss_pct}%</div>
        <div><strong>Max Consec. Losses</strong><br>{rb.max_consecutive_losses}</div>
        <div><strong>Risk/Trade</strong><br>${rb.risk_per_trade_usd}</div>
        <div><strong>Allowed Sessions</strong><br>{", ".join(rb.allowed_sessions)}</div>
      </div>"""
    rb_section = section("💰 Risk Budget", rb_html)

    # ── Operator Actions
    priority_col = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#64748b"}
    cat_icons = {"CHECK": "🔍", "AVOID": "🚫", "MONITOR": "👁", "EXECUTE": "✅"}
    act_html = ""
    for a in pack.operator_actions:
        col = priority_col.get(a.priority, "#94a3b8")
        icon = cat_icons.get(a.category, "•")
        act_html += f"""
        <div style="display:flex;gap:0.75rem;align-items:flex-start;padding:0.6rem 0;border-bottom:1px solid #1e2433;">
          <span style="font-size:1.1rem;">{icon}</span>
          <div>
            <span style="color:{col};font-size:0.7rem;font-weight:700;">[{a.priority}] {a.category}</span><br>
            <span style="font-size:0.875rem;">{a.description}</span>
          </div>
        </div>"""
    actions_section = section("✅ Operator Actions", act_html)

    # ── Delta
    delta_section = ""
    if pack.delta_from_previous:
        d = pack.delta_from_previous
        delta_html = f"""
          <p><strong>Compared to:</strong> {d.previous_briefing_id or "N/A"}</p>
          <p>{d.summary}</p>
          {"<p>New tickets: " + ", ".join(d.new_tickets) + "</p>" if d.new_tickets else ""}
          {"<p>New incidents: " + str(d.incident_count_delta) + "</p>" if d.incident_count_delta else ""}"""
        delta_section = section("🔄 Delta from Previous", delta_html)

    # ── Full page
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Session Briefing — {pack.session_label} {pack.date}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.75rem; margin-bottom: 0.25rem; }}
    @media print {{
      body {{ background: #fff; color: #111; padding: 1rem; }}
      button {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2rem;">
    <div>
      <h1>Session Briefing Pack</h1>
      <p style="color:{session_color};font-size:1rem;font-weight:600;">{pack.session_label} SESSION — {pack.date}</p>
      <p style="color:#64748b;font-size:0.8rem;">{pack.briefing_id} | Generated: {pack.created_at.strftime("%Y-%m-%d %H:%M:%S")} EAT</p>
      <div style="margin-top:0.5rem;">{type_badge}</div>
    </div>
    <button onclick="window.print()"
      style="background:#3b82f6;color:#fff;border:none;padding:0.6rem 1.2rem;border-radius:8px;cursor:pointer;font-size:0.875rem;">
      🖨 Print / PDF
    </button>
  </div>
  {warnings_html}
  {sys_section}
  {mkt_section}
  {pairs_section}
  {rb_section}
  {actions_section}
  {delta_section}
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────────────────────────────────

BRIEFINGS_DIR = os.path.join("artifacts", "briefings")


def save_briefing_artifact(pack: BriefingPack) -> str:
    """Render HTML and write to artifacts/briefings/. Returns relative path."""
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    filename = f"{pack.briefing_id}.html"
    path = os.path.join(BRIEFINGS_DIR, filename)
    html = render_briefing_html(pack)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Briefing artifact saved: {path}")
    return path


def persist_briefing(pack: BriefingPack, db: Session) -> SessionBriefing:
    """Persist a BriefingPack to the DB (and HTML artifact)."""
    html_path = save_briefing_artifact(pack)

    record = SessionBriefing(
        briefing_id=pack.briefing_id,
        session_label=pack.session_label,
        date=pack.date,
        is_delta=pack.is_delta,
        html_path=html_path,
        data=pack.model_dump(mode="json"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
