"""
shared/logic/execution_logic.py
PreflightEngine — safe-failure edition.

News-window check (check #5):
  FAIL CLOSED if no MarketContextPacket found in DB — treats absent data
  as a potential news window rather than silently passing.
"""

import logging
import yaml
from datetime import datetime
from typing import List, Optional

from shared.database.models import KillSwitch, OrderTicket, Packet, IncidentLog
from shared.types.execution_prep import PreflightCheck
from shared.logic.sessions import get_nairobi_time

logger = logging.getLogger("PreflightEngine")


def load_exec_config() -> dict:
    try:
        with open("config/execution_prep.yaml", "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("execution_prep.yaml not found — using defaults.")
        return {}


class PreflightEngine:
    def __init__(self, db_session):
        self.db = db_session
        self.config = load_exec_config()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_incident(self, severity: str, message: str) -> None:
        logger.error("[INCIDENT][%s] PreflightEngine — %s", severity, message)
        try:
            self.db.add(
                IncidentLog(
                    severity=severity, component="PreflightEngine", message=message
                )
            )
            self.db.commit()
        except Exception as exc:
            logger.error("Failed to persist preflight incident: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_checks(
        self,
        ticket: OrderTicket,
        current_price: Optional[float] = None,
        current_spread: Optional[float] = None,
    ) -> List[PreflightCheck]:
        checks: List[PreflightCheck] = []
        now = get_nairobi_time()

        # Fetch live data if not provided
        if current_price is None or current_spread is None:
            from shared.providers.price_quote import get_price_quote_provider

            provider = get_price_quote_provider()
            quote = provider.get_quote(ticket.pair)
            if quote:
                current_price = (
                    current_price if current_price is not None else quote.mid
                )
                current_spread = (
                    current_spread if current_spread is not None else quote.spread_pips
                )
            else:
                self._log_incident(
                    "ERROR",
                    f"No live quote found for {ticket.pair}. Preflight failing closed.",
                )

        # ── 1. Expiry ────────────────────────────────────────────────────
        expires_at = ticket.expires_at
        if expires_at and expires_at.tzinfo is None:
            import pytz

            expires_at = pytz.utc.localize(expires_at).astimezone(
                pytz.timezone("Africa/Nairobi")
            )

        is_expired = expires_at and now > expires_at
        checks.append(
            PreflightCheck(
                id="expiry",
                name="Ticket Expiry",
                status="PASS" if not is_expired else "FAIL",
                details="Ticket is active"
                if not is_expired
                else f"Ticket expired at {expires_at}",
            )
        )

        # ── 2. Kill Switch ───────────────────────────────────────────────
        active_ks = self.db.query(KillSwitch).filter(KillSwitch.is_active == 1).first()
        checks.append(
            PreflightCheck(
                id="kill_switch",
                name="System Kill Switch",
                status="PASS" if not active_ks else "FAIL",
                details="All systems operational"
                if not active_ks
                else f"Kill switch active: {active_ks.switch_type}",
            )
        )

        # ── 3. Price Tolerance ───────────────────────────────────────────
        if current_price is None:
            status, details = "FAIL", "FAIL-CLOSED: Live price unavailable"
        else:
            deviation = (
                abs(current_price - ticket.entry_price) / ticket.entry_price * 100
            )
            tolerance = self.config.get("price_tolerance_pct", 0.1)
            status = "PASS" if deviation <= tolerance else "FAIL"
            details = f"Current deviation {deviation:.3f}% (Max {tolerance}%)"

        checks.append(
            PreflightCheck(
                id="price_deviation",
                name="Price Tolerance",
                status=status,
                details=details,
            )
        )

        # ── 4. Spread ────────────────────────────────────────────────────
        if current_spread is None:
            status, details = "FAIL", "FAIL-CLOSED: Live spread unavailable"
        else:
            max_spread = self.config.get("max_spread_pips", 3.0)
            status = "PASS" if current_spread <= max_spread else "WARN"
            details = f"Current spread {current_spread:.1f} pips (Max recommended {max_spread})"

        checks.append(
            PreflightCheck(
                id="spread",
                name="Market Spread",
                status=status,
                details=details,
            )
        )

        # ── 5. News Window — FAIL CLOSED ─────────────────────────────────
        context = (
            self.db.query(Packet)
            .filter(Packet.packet_type == "MarketContextPacket")
            .order_by(Packet.created_at.desc())
            .first()
        )

        if context is None:
            # No market-context data at all — FAIL CLOSED and log incident
            self._log_incident(
                "WARNING",
                "No MarketContextPacket found in DB. Unable to verify news-window safety. "
                "Failing execution preflight news check (fail-closed policy).",
            )
            checks.append(
                PreflightCheck(
                    id="news_window",
                    name="News Proximity",
                    status="FAIL",
                    details=(
                        "FAIL-CLOSED: No MarketContextPacket available. "
                        "Cannot verify news windows — treating as unsafe."
                    ),
                )
            )
            return checks

        # Context exists — check freshness (warn if context is stale > 2h)
        try:
            ctx_age_hours = (
                now - context.created_at.replace(tzinfo=now.tzinfo)
            ).total_seconds() / 3600
            if ctx_age_hours > 2:
                logger.warning(
                    "MarketContextPacket is %.1f hours old — news-window check may be stale.",
                    ctx_age_hours,
                )
        except Exception:
            pass

        # Check first-class no_trade_windows field, fall back to data dict
        windows = (
            context.data.get("no_trade_windows", [])
            if isinstance(context.data, dict)
            else []
        )

        in_window = False
        window_details = "No high-impact red events in immediate window"

        for window in windows:
            start_str = window.get("start")
            end_str = window.get("end")
            event_name = window.get("event", "Unknown Event")
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if start_dt <= now <= end_dt:
                    in_window = True
                    window_details = (
                        f"Inside no-trade window for: {event_name} "
                        f"(until {end_dt.strftime('%H:%M')} EAT)"
                    )
                    break
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("Skipping malformed no-trade window %s: %s", window, exc)
                continue

        checks.append(
            PreflightCheck(
                id="news_window",
                name="News Proximity",
                status="PASS" if not in_window else "FAIL",
                details=window_details,
            )
        )

        return checks
