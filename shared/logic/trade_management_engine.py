# ruff: noqa: E402  # delayed imports/path setup required in this module
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from shared.database.models import (
    KillSwitch,
    ManagementSuggestionLog,
    OrderTicket,
    PolicySelectionLog,
    PositionSnapshot,
    TicketTradeLink,
)
from shared.logic.sessions import get_nairobi_time
from shared.providers.price_quote import PriceQuoteProvider, get_price_quote_provider
from shared.types.trade_management import PositionManagementSuggestion, SuggestionType

logger = logging.getLogger("TradeManagementEngine")


def calculate_r_multiple(
    side: str, entry_price: float, sl: float, current_price: float
) -> float:
    """Calculate the current R multiple (Risk/Reward ratio progress)."""
    risk = abs(entry_price - sl)
    if risk == 0:
        return 0.0

    if side.upper() == "BUY":
        profit = current_price - entry_price
    else:
        profit = entry_price - current_price

    return profit / risk


from shared.providers.calendar import get_calendar_provider


def generate_suggestions_for_position(
    db: Session,
    snapshot: PositionSnapshot,
    quote_provider: PriceQuoteProvider,
    now_eat: datetime,
) -> list[PositionManagementSuggestion]:
    """Generate rule-based suggestions for a single position snapshot."""
    # 1. Find the linked ticket
    link = (
        db.query(TicketTradeLink)
        .filter(TicketTradeLink.broker_trade_id == snapshot.position_id)
        .first()
    )
    if not link:
        return []

    ticket = (
        db.query(OrderTicket).filter(OrderTicket.ticket_id == link.ticket_id).first()
    )
    if not ticket:
        return []

    # 2. Get current quote
    quote = quote_provider.get_quote(snapshot.symbol)
    if not quote:
        logger.warning(f"No quote available for {snapshot.symbol}")
        return []

    current_price = quote.bid if snapshot.side == "BUY" else quote.ask
    current_r = calculate_r_multiple(
        snapshot.side, snapshot.avg_price, snapshot.sl, current_price
    )

    suggestions = []

    # Rule: Kill Switch Active
    active_ks = (
        db.query(KillSwitch)
        .filter(KillSwitch.is_active, KillSwitch.switch_type.in_(["GLOBAL", "TRADING"]))
        .first()
    )

    if active_ks:
        suggestions.append(
            PositionManagementSuggestion(
                created_at_eat=now_eat,
                ticket_id=ticket.id,
                broker_trade_id=snapshot.position_id,
                symbol=snapshot.symbol,
                side=snapshot.side,
                lots=snapshot.lots,
                entry_price=snapshot.avg_price,
                sl=snapshot.sl,
                tp1=ticket.take_profit_1,
                tp2=ticket.take_profit_2,
                current_price=current_price,
                current_r=current_r,
                suggestion_type=SuggestionType.NO_ACTION,
                severity="CRITICAL",
                reasons=[
                    f"Kill Switch Active: {active_ks.switch_type} - Manually Manage"
                ],
                expires_at_eat=now_eat + timedelta(minutes=15),
                instruction="Halt Trading - Manage manually",
            )
        )
        # If kill switch is active, don't generate other suggestions
        return suggestions

    # Rule: End of NY Session (00:30 to 01:00 EAT)
    current_time = now_eat.time()
    if (
        current_time >= datetime.strptime("00:30", "%H:%M").time()
        and current_time < datetime.strptime("01:00", "%H:%M").time()
    ):
        suggestions.append(
            PositionManagementSuggestion(
                created_at_eat=now_eat,
                ticket_id=ticket.id,
                broker_trade_id=snapshot.position_id,
                symbol=snapshot.symbol,
                side=snapshot.side,
                lots=snapshot.lots,
                entry_price=snapshot.avg_price,
                sl=snapshot.sl,
                tp1=ticket.take_profit_1,
                tp2=ticket.take_profit_2,
                current_price=current_price,
                current_r=current_r,
                suggestion_type=SuggestionType.CLOSE_END_OF_SESSION,
                severity="WARN",
                reasons=["NY Session ends at 01:00 EAT"],
                expires_at_eat=now_eat + timedelta(minutes=15),
                instruction="Close Position - End of Session",
            )
        )

    # Rule: Strict Risk Policy Checks
    policy_log = (
        db.query(PolicySelectionLog)
        .filter(PolicySelectionLog.pair == ticket.pair)
        .order_by(PolicySelectionLog.created_at.desc())
        .first()
    )
    if policy_log and policy_log.policy_name == "RISK_OFF" and current_r >= 0.5:
        suggestions.append(
            PositionManagementSuggestion(
                created_at_eat=now_eat,
                ticket_id=ticket.id,
                broker_trade_id=snapshot.position_id,
                symbol=snapshot.symbol,
                side=snapshot.side,
                lots=snapshot.lots,
                entry_price=snapshot.avg_price,
                sl=snapshot.sl,
                tp1=ticket.take_profit_1,
                tp2=ticket.take_profit_2,
                current_price=current_price,
                current_r=current_r,
                suggestion_type=SuggestionType.REDUCE_RISK,
                severity="WARN",
                reasons=[
                    "RISK_OFF policy active: Taking partial profit early at >= 0.5R"
                ],
                expires_at_eat=now_eat + timedelta(minutes=15),
                instruction=f"Take Partial Profit (RISK_OFF): {(snapshot.lots / 2):.2f} lots",
            )
        )

    # Rule: Move SL to BE at 1.0R
    if current_r >= 1.0:
        is_already_be = False
        if snapshot.side == "BUY":
            is_already_be = snapshot.sl >= (snapshot.avg_price - 0.00001)
        else:
            is_already_be = snapshot.sl <= (snapshot.avg_price + 0.00001)

        if not is_already_be:
            suggestions.append(
                PositionManagementSuggestion(
                    created_at_eat=now_eat,
                    ticket_id=ticket.id,
                    broker_trade_id=snapshot.position_id,
                    symbol=snapshot.symbol,
                    side=snapshot.side,
                    lots=snapshot.lots,
                    entry_price=snapshot.avg_price,
                    sl=snapshot.sl,
                    tp1=ticket.take_profit_1,
                    tp2=ticket.take_profit_2,
                    current_price=current_price,
                    current_r=current_r,
                    suggestion_type=SuggestionType.MOVE_SL_TO_BE,
                    severity="WARN",
                    reasons=[f"Price reached {current_r:.2f}R"],
                    expires_at_eat=now_eat + timedelta(minutes=15),
                    instruction=f"Move SL to Entry: {snapshot.avg_price:.5f}",
                )
            )

    # Rule: Partial TP1
    if ticket.take_profit_1:
        hit_tp1 = False
        if snapshot.side == "BUY":
            hit_tp1 = current_price >= ticket.take_profit_1
        else:
            hit_tp1 = current_price <= ticket.take_profit_1

        if hit_tp1:
            suggestions.append(
                PositionManagementSuggestion(
                    created_at_eat=now_eat,
                    ticket_id=ticket.id,
                    broker_trade_id=snapshot.position_id,
                    symbol=snapshot.symbol,
                    side=snapshot.side,
                    lots=snapshot.lots,
                    entry_price=snapshot.avg_price,
                    sl=snapshot.sl,
                    tp1=ticket.take_profit_1,
                    tp2=ticket.take_profit_2,
                    current_price=current_price,
                    current_r=current_r,
                    suggestion_type=SuggestionType.TAKE_PARTIAL_TP1,
                    severity="CRITICAL",
                    reasons=[f"Price hit TP1: {ticket.take_profit_1:.5f}"],
                    expires_at_eat=now_eat + timedelta(minutes=15),
                    instruction=f"Take Partial Profit TP1 (Close 50%): {(snapshot.lots / 2):.2f} lots",
                )
            )

    # Rule: Partial TP2 / Full Close
    if ticket.take_profit_2:
        hit_tp2 = False
        if snapshot.side == "BUY":
            hit_tp2 = current_price >= ticket.take_profit_2
        else:
            hit_tp2 = current_price <= ticket.take_profit_2

        if hit_tp2:
            suggestions.append(
                PositionManagementSuggestion(
                    created_at_eat=now_eat,
                    ticket_id=ticket.id,
                    broker_trade_id=snapshot.position_id,
                    symbol=snapshot.symbol,
                    side=snapshot.side,
                    lots=snapshot.lots,
                    entry_price=snapshot.avg_price,
                    sl=snapshot.sl,
                    tp1=ticket.take_profit_1,
                    tp2=ticket.take_profit_2,
                    current_price=current_price,
                    current_r=current_r,
                    suggestion_type=SuggestionType.TAKE_PARTIAL_CUSTOM,
                    severity="CRITICAL",
                    reasons=[f"Price hit TP2: {ticket.take_profit_2:.5f}"],
                    expires_at_eat=now_eat + timedelta(minutes=15),
                    instruction=f"Take TP2 / Full Close: {snapshot.lots:.2f} lots",
                )
            )

    # Rule: News warning
    calendar = get_calendar_provider()
    events = calendar.fetch_events()
    now_utc = datetime.now(timezone.utc)
    for ev in events:
        # Calendar events store time as HH:MM (same contract used in guardrails.py).
        # Reconstruct a full UTC datetime by placing the HH:MM on today or tomorrow.
        try:
            ev_time_str = ev.get("time", "")
            ev_naive = datetime.strptime(ev_time_str, "%H:%M")
            # Build today's candidate in UTC
            ev_today_utc = now_utc.replace(
                hour=ev_naive.hour,
                minute=ev_naive.minute,
                second=0,
                microsecond=0,
            )
            # If that time has already passed, use tomorrow
            ev_time = (
                ev_today_utc
                if ev_today_utc >= now_utc
                else ev_today_utc + timedelta(days=1)
            )
        except (ValueError, AttributeError):
            continue
        if now_utc < ev_time < now_utc + timedelta(minutes=60):
            # Check if currency relates to symbol
            if ev["currency"] in snapshot.symbol:
                suggestions.append(
                    PositionManagementSuggestion(
                        created_at_eat=now_eat,
                        ticket_id=ticket.id,
                        broker_trade_id=snapshot.position_id,
                        symbol=snapshot.symbol,
                        side=snapshot.side,
                        lots=snapshot.lots,
                        entry_price=snapshot.avg_price,
                        sl=snapshot.sl,
                        tp1=ticket.take_profit_1,
                        tp2=ticket.take_profit_2,
                        current_price=current_price,
                        current_r=current_r,
                        suggestion_type=SuggestionType.EXIT_BEFORE_NEWS,
                        severity="WARN",
                        reasons=[
                            f"High impact news ({ev['event']}) in {int((ev_time - now_utc).total_seconds() / 60)} mins"
                        ],
                        expires_at_eat=now_eat + timedelta(minutes=15),
                        instruction="Close Position Before News",
                    )
                )
                break

    return suggestions


def run_management_cycle(db: Session):
    """Run the full management cycle for all open positions."""
    now_eat = get_nairobi_time()
    quote_provider = get_price_quote_provider()

    # Filter to recently-updated snapshots only.
    # PositionSnapshot has no explicit status column; positions that have not
    # been updated in the last 4 hours are treated as closed/gone.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    snapshots = (
        db.query(PositionSnapshot)
        .filter(PositionSnapshot.updated_at_utc >= cutoff)
        .all()
    )

    for snapshot in snapshots:
        suggestions = generate_suggestions_for_position(
            db, snapshot, quote_provider, now_eat
        )

        for sug in suggestions:
            # Create time bucket for hourly dedup (or similar)
            time_bucket = f"{now_eat.strftime('%Y-%m-%d-%H')}"

            # Persist if not already exists in this bucket
            try:
                # Check for existing
                existing = (
                    db.query(ManagementSuggestionLog)
                    .filter(
                        ManagementSuggestionLog.ticket_id == str(sug.ticket_id),
                        ManagementSuggestionLog.suggestion_type
                        == sug.suggestion_type.value,
                        ManagementSuggestionLog.time_bucket == time_bucket,
                    )
                    .first()
                )

                if not existing:
                    log_entry = ManagementSuggestionLog(
                        ticket_id=str(sug.ticket_id),
                        broker_trade_id=sug.broker_trade_id,
                        suggestion_type=sug.suggestion_type.value,
                        severity=sug.severity,
                        data=sug.model_dump(mode="json"),
                        time_bucket=time_bucket,
                        expires_at=sug.expires_at_eat,
                    )
                    db.add(log_entry)
                    db.commit()
                    logger.info(
                        f"Generated suggestion {sug.suggestion_type} for ticket {sug.ticket_id}"
                    )

                    # Notify
                    from shared.logic.notifications import (
                        notify_suggestion as send_notif,
                    )

                    send_notif(sug.model_dump(mode="json"))
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to log suggestion: {e}")
