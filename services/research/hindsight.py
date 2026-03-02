import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import httpx

from shared.database.models import OrderTicket, HindsightOutcomeLog
from shared.types.hindsight import HindsightOutcome
from shared.types.packets import Candle

logger = logging.getLogger("HindsightEngine")


def _log_hindsight_event(ticket_id: str, outcome_label: str, realized_r: float):
    """Helper to send hindsight results to Journal Service."""
    try:
        httpx.post(
            "http://localhost:8004/log/ticket_transition",
            json={
                "hindsight_outcome": outcome_label,
                "hindsight_realized_r": realized_r,
            },
            params={"ticket_id": ticket_id, "transition_type": "HINDSIGHT_COMPUTED"},
            timeout=2.0,
        )
    except Exception as e:
        logger.warning(f"Failed to log HINDSIGHT_COMPUTED for {ticket_id}: {e}")


def walk_forward(
    ticket: OrderTicket, future_candles: List[Candle], max_candles: int = 1440
) -> HindsightOutcome:
    """
    Simulates a skipped/expired ticket. If the target is not hit within max_candles (e.g. 1 day of 1m candles),
    it returns a NONE state to cap the search horizon.
    """
    if ticket.status not in ["SKIPPED", "EXPIRED"]:
        return HindsightOutcome(
            ticket_id=ticket.ticket_id,
            computed_at=datetime.now(timezone.utc),
            outcome_label="NONE",
            realized_r=0.0,
            first_hit="NONE",
            notes=f"Ticket status was {ticket.status}, not evaluatable.",
        )

    is_long = ticket.direction.upper() == "BUY"
    entry = ticket.entry_price
    sl = ticket.stop_loss
    tp1 = ticket.take_profit_1

    risk_dist = entry - sl if is_long else sl - entry
    if risk_dist <= 0:
        return HindsightOutcome(
            ticket_id=ticket.ticket_id,
            computed_at=datetime.now(timezone.utc),
            outcome_label="NONE",
            realized_r=0.0,
            first_hit="NONE",
            notes="Invalid risk distance.",
        )

    # Simplified break-even trigger rule (1R = Move stops)
    be_level = entry + risk_dist if is_long else entry - risk_dist
    sl_moved_to_be = False

    for i, candle in enumerate(future_candles):
        if i >= max_candles:
            return HindsightOutcome(
                ticket_id=ticket.ticket_id,
                computed_at=datetime.now(timezone.utc),
                outcome_label="NONE",
                realized_r=0.0,
                first_hit="NONE",
                time_to_hit_min=i,
                notes="Max horizon reached.",
            )

        high = candle.high
        low = candle.low

        if is_long:
            hit_sl = low <= sl
            hit_tp1 = high >= tp1

            if hit_sl and hit_tp1:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="BE" if sl_moved_to_be else "LOSS",
                    realized_r=0.0 if sl_moved_to_be else -1.0,
                    first_hit="SL",
                    time_to_hit_min=i,
                )

            if hit_sl:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="BE" if sl_moved_to_be else "LOSS",
                    realized_r=0.0 if sl_moved_to_be else -1.0,
                    first_hit="SL",
                    time_to_hit_min=i,
                )

            if hit_tp1:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="WIN",
                    realized_r=(tp1 - entry) / risk_dist,
                    first_hit="TP1",
                    time_to_hit_min=i,
                )

            if not sl_moved_to_be and high >= be_level:
                sl_moved_to_be = True
                sl = entry

        else:  # SHORT
            hit_sl = high >= sl
            hit_tp1 = low <= tp1

            if hit_sl and hit_tp1:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="BE" if sl_moved_to_be else "LOSS",
                    realized_r=0.0 if sl_moved_to_be else -1.0,
                    first_hit="SL",
                    time_to_hit_min=i,
                )

            if hit_sl:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="BE" if sl_moved_to_be else "LOSS",
                    realized_r=0.0 if sl_moved_to_be else -1.0,
                    first_hit="SL",
                    time_to_hit_min=i,
                )

            if hit_tp1:
                return HindsightOutcome(
                    ticket_id=ticket.ticket_id,
                    computed_at=datetime.now(timezone.utc),
                    outcome_label="WIN",
                    realized_r=(entry - tp1) / risk_dist,
                    first_hit="TP1",
                    time_to_hit_min=i,
                )

            if not sl_moved_to_be and low <= be_level:
                sl_moved_to_be = True
                sl = entry

    # End of dataset
    return HindsightOutcome(
        ticket_id=ticket.ticket_id,
        computed_at=datetime.now(timezone.utc),
        outcome_label="NONE",
        realized_r=0.0,
        first_hit="NONE",
        time_to_hit_min=len(future_candles),
        notes="Dataset exhausted.",
    )


def process_ticket_hindsight(
    db: Session, ticket_id: str, candles: List[Candle]
) -> Optional[HindsightOutcome]:
    """Wraps walk_forward, persisting to DB and triggering Journal."""
    ticket = db.query(OrderTicket).filter(OrderTicket.ticket_id == ticket_id).first()
    if not ticket or ticket.hindsight_status != "PENDING":
        return None

    outcome = walk_forward(ticket, candles)

    # Save log
    log_db = HindsightOutcomeLog(
        ticket_id=ticket.ticket_id,
        computed_at=outcome.computed_at,
        outcome_label=outcome.outcome_label,
        realized_r=outcome.realized_r,
        first_hit=outcome.first_hit,
        time_to_hit_min=outcome.time_to_hit_min,
        notes=outcome.notes,
    )
    db.add(log_db)

    # Update ticket
    ticket.hindsight_status = "DONE"
    ticket.hindsight_outcome_label = outcome.outcome_label
    ticket.hindsight_realized_r = outcome.realized_r

    db.commit()

    # Fire event
    _log_hindsight_event(ticket.ticket_id, outcome.outcome_label, outcome.realized_r)
    return outcome


def run_hindsight_for_date(db: Session, target_date: str, csv_path: str) -> dict:
    """Finds all SKIPPED/EXPIRED tickets for a date and evaluates them."""
    # Note: In a real system, `csv_path` would be dynamically chosen by the pair.
    # We pass it explicitly here for the mock constraints.
    import pandas as pd
    from sqlalchemy import func

    parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    tickets = (
        db.query(OrderTicket)
        .filter(
            OrderTicket.status.in_(["SKIPPED", "EXPIRED"]),
            OrderTicket.hindsight_status == "PENDING",
            func.date(OrderTicket.created_at) == parsed_date,
        )
        .all()
    )

    if not tickets:
        return {"processed": 0, "status": "no tickets found"}

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])

    processed = 0
    for t in tickets:
        # Get candles AFTER the ticket was created
        future_df = df[df["timestamp"] >= pd.to_datetime(t.created_at)].copy()
        future_df.sort_values("timestamp", inplace=True)

        candles = []
        for _, row in future_df.iterrows():
            candles.append(
                Candle(
                    timestamp=row["timestamp"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row.get("volume", 0),
                )
            )

        process_ticket_hindsight(db, t.ticket_id, candles)
        processed += 1

    return {"processed": processed}


def get_hindsight_summary(db: Session, target_date: str) -> dict:
    """Aggregates decision quality metrics for a given date."""
    from datetime import timedelta

    parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    start_of_day = datetime.combine(
        parsed_date, datetime.min.time(), tzinfo=timezone.utc
    )
    end_of_day = start_of_day + timedelta(days=1)

    logs = (
        db.query(HindsightOutcomeLog)
        .join(OrderTicket)
        .filter(
            OrderTicket.created_at >= start_of_day, OrderTicket.created_at < end_of_day
        )
        .all()
    )

    if not logs:
        return {"total": 0}

    # Breakdown by Skip Reason
    reasons = {}
    for log in logs:
        reason = log.ticket.skip_reason or "EXPIRED"
        if reason not in reasons:
            reasons[reason] = {"count": 0, "wins": 0, "losses": 0, "total_r": 0.0}

        reasons[reason]["count"] += 1
        if log.outcome_label == "WIN":
            reasons[reason]["wins"] += 1
        elif log.outcome_label == "LOSS":
            reasons[reason]["losses"] += 1

        reasons[reason]["total_r"] += log.realized_r

    # Formatting
    summary_reasons = []
    for r, d in reasons.items():
        summary_reasons.append(
            {
                "reason": r,
                "count": d["count"],
                "win_rate": round(d["wins"] / d["count"] * 100, 1)
                if d["count"] > 0
                else 0.0,
                "avg_r": round(d["total_r"] / d["count"], 2) if d["count"] > 0 else 0.0,
            }
        )

    # Costliest miss
    costliest = max(logs, key=lambda x: x.realized_r) if logs else None

    return {
        "total": len(logs),
        "reasons": summary_reasons,
        "costliest_miss": {
            "ticket_id": costliest.ticket_id,
            "reason": costliest.ticket.skip_reason,
            "missed_r": costliest.realized_r,
        }
        if costliest and costliest.realized_r > 0
        else None,
    }


def generate_hindsight_report(db: Session, target_date: str) -> str:
    """Creates an HTML report for the day's hindsight metrics."""
    import os

    summary = get_hindsight_summary(db, target_date)

    if summary["total"] == 0:
        return ""

    os.makedirs("artifacts/hindsight", exist_ok=True)
    report_path = f"artifacts/hindsight/report_{target_date}.html"

    rows = ""
    for r in summary.get("reasons", []):
        rows += f"<tr><td>{r['reason']}</td><td>{r['count']}</td><td>{r['win_rate']}%</td><td>{r['avg_r']} R</td></tr>"

    costliest_html = ""
    if summary.get("costliest_miss"):
        c = summary["costliest_miss"]
        costliest_html = f"<div class='alert'>Costliest Skip: <b>{c['ticket_id']}</b> ({c['reason']}) missed out on <b>+{c['missed_r']} R</b>.</div>"

    html = f"""
    <html>
    <head><style>
        body {{ font-family: sans-serif; padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
        th {{ background: #f4f4f4; }}
        .alert {{ color: #d35400; padding: 10px; background: #fdf2e9; border-left: 4px solid #d35400; margin-top: 20px; }}
    </style></head>
    <body>
        <h2>Hindsight Decision Quality Report - {target_date}</h2>
        <p>Total Evaluated: {summary["total"]}</p>
        
        {costliest_html}
        
        <h3>Skip Reasons Breakdown</h3>
        <table>
            <tr><th>Reason</th><th>Count</th><th>Win Rate</th><th>Avg Output (R)</th></tr>
            {rows}
        </table>
    </body>
    </html>
    """

    with open(report_path, "w") as f:
        f.write(html)

    return report_path
