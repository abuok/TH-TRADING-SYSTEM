"""
shared/logic/guardrails.py
PHX v2 Strategy Guardrails Engine.

Evaluates 7 rules against a TechnicalSetupPacket and surrounding context,
producing a GuardrailsResult with discipline_score (0–100) and hard_block flag.
All times validated in Africa/Nairobi (UTC+3).
"""

import os
import logging
from datetime import datetime, timezone, timedelta, time as time_
from typing import Any, Dict, List, Optional

import pytz
import yaml
from sqlalchemy.orm import Session

from shared.database.models import GuardrailsLog, OrderTicket
from shared.logic.sessions import get_nairobi_time
from shared.types.guardrails import (
    EvidenceRef,
    GuardrailsResult,
    RuleCheck,
    GUARDRAILS_VERSION,
)

logger = logging.getLogger("GuardrailsEngine")
NAIROBI = pytz.timezone("Africa/Nairobi")

# ──────────────────────────────────────────────────────────────────────────
# Config loader
# ──────────────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = os.path.join("config", "guardrails_config.yaml")


def load_config(path: str = _DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """
    Load guardrails config from YAML with optional env-variable overrides.
    Env format: GUARDRAILS_<KEY_UPPER> (e.g. GUARDRAILS_MIN_SETUP_SCORE=75)
    """
    cfg: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # Apply env overrides for scalar values
    scalar_keys = [
        "quote_staleness_limit_seconds",
        "news_buffer_minutes",
        "phx_min_stages_required",
        "displacement_min_candle_ratio",
        "min_setup_score",
        "max_consecutive_losses",
        "max_daily_loss_pct",
        "duplicate_suppression_window_minutes",
        "score_deduction_fail",
        "score_deduction_warn",
    ]
    for key in scalar_keys:
        env_key = f"GUARDRAILS_{key.upper()}"
        env_val = os.getenv(env_key)
        if env_val is not None:
            try:
                cfg[key] = type(cfg.get(key, 0))(env_val)
            except (ValueError, TypeError):
                cfg[key] = env_val

    # Defaults
    cfg.setdefault("news_buffer_minutes", 30)
    cfg.setdefault("phx_min_stages_required", 4)
    cfg.setdefault("displacement_min_candle_ratio", 0.67)
    cfg.setdefault("min_setup_score", 70)
    cfg.setdefault("max_consecutive_losses", 3)
    cfg.setdefault("max_daily_loss_pct", 2.0)
    cfg.setdefault("duplicate_suppression_window_minutes", 60)
    cfg.setdefault("quote_staleness_limit_seconds", 15.0)
    cfg.setdefault("score_deduction_fail", 20)
    cfg.setdefault("score_deduction_warn", 5)
    cfg.setdefault("news_window_hard_block", True)
    cfg.setdefault("phx_sequence_hard_block", False)
    cfg.setdefault("displacement_quality_hard_block", False)
    cfg.setdefault("setup_score_hard_block", False)
    cfg.setdefault("risk_state_hard_block", True)
    cfg.setdefault("duplicate_suppression_hard_block", False)
    cfg.setdefault(
        "session_windows",
        {
            "LONDON": {"start": "11:00", "end": "20:00"},
            "NEW YORK": {"start": "16:00", "end": "01:00"},
        },
    )
    cfg.setdefault("allowed_sessions", ["LONDON", "NEW YORK"])
    return cfg


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _parse_time(t: str) -> time_:
    h, m = t.split(":")
    return time_(int(h), int(m), tzinfo=None)


def _time_in_window(t: time_, start_str: str, end_str: str) -> bool:
    """Check if time t is inside [start, end] — supports midnight-crossing windows."""
    start = _parse_time(start_str)
    end = _parse_time(end_str)
    t_plain = time_(t.hour, t.minute)
    if end > start:  # same-day window
        return start <= t_plain <= end
    else:  # midnight-crossing
        return t_plain >= start or t_plain <= end


def _stage_index(stage_name: str) -> int:
    """Return ordinal index for a PHX stage name (for completeness checks)."""
    order = ["IDLE", "BIAS", "SWEEP", "DISPLACE", "CHOCH_BOS", "RETEST", "TRIGGER"]
    try:
        return order.index(stage_name.upper())
    except ValueError:
        return 0


# PHX stage ordinals for scoring
_PHX_STAGE_ORDER = [
    "IDLE",
    "BIAS",
    "SWEEP",
    "DISPLACE",
    "CHOCH_BOS",
    "RETEST",
    "TRIGGER",
]


# ──────────────────────────────────────────────────────────────────────────
# Individual rule evaluators
# ──────────────────────────────────────────────────────────────────────────

# Removed _rule_session_window -> Migrated to AlignmentEngine
# Removed _rule_news_window -> Migrated to AlignmentEngine

def _rule_eod_gap(now_nairobi: datetime, cfg: Dict) -> RuleCheck:
    """GR-E01: Block trading around broker End Of Day (00:00 EET) due to spread widening."""
    # Convert Nairobi time to broker time (EET/EEST)
    eet_tz = pytz.timezone("EET")
    now_eet = now_nairobi.astimezone(eet_tz)
    t = now_eet.time()

    # Block from 23:55 to 00:10 broker server time
    hard = True
    eod_start = time_(23, 55)
    eod_end = time_(0, 10)

    # Check if time crosses midnight broker time
    is_gap = t >= eod_start or t <= eod_end

    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="broker_eet_time",
            value=now_eet.strftime("%H:%M"),
            description="Broker Server Time (EET/EEST)",
        )
    ]

    if is_gap:
        return RuleCheck(
            id="GR-E01",
            name="End of Day Broker Gap",
            status="FAIL",
            details=f"Current broker time {now_eet.strftime('%H:%M')} is inside the EOD rollover spread-widening gap (23:55-00:10).",
            is_mandatory=hard,
            deduction=cfg.get("score_deduction_fail", 20),
            evidence_refs=evidence,
        )
    return RuleCheck(
        id="GR-E01",
        name="End of Day Broker Gap",
        status="PASS",
        details=f"Current broker time {now_eet.strftime('%H:%M')} is outside EOD gap.",
        is_mandatory=hard,
        deduction=0,
        evidence_refs=evidence,
    )


def _rule_phx_sequence(setup_data: Dict, cfg: Dict) -> RuleCheck:
    """GR-P01: Does the setup reach the minimum required PHX stage?"""
    stage_name = setup_data.get(
        "stage", setup_data.get("strategy_name", "IDLE")
    ).upper()
    stage_idx = _stage_index(stage_name)
    min_required = int(cfg["phx_min_stages_required"])
    hard = cfg.get("phx_sequence_hard_block", False)

    # Build evidence of which stages are present
    stage_ts = setup_data.get("stage_timestamps", {})
    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="current_stage",
            value=stage_name,
            description=f"Ordinal {stage_idx}/{len(_PHX_STAGE_ORDER) - 1}",
        )
    ]
    if stage_ts:
        evidence.append(
            EvidenceRef(
                ref_type="metric",
                key="stage_timestamps",
                value=stage_ts,
                description="PHX stage timestamps",
            )
        )

    if stage_idx >= min_required:
        min_name = _PHX_STAGE_ORDER[min_required]
        return RuleCheck(
            id="GR-P01",
            name="PHX Sequence Completeness",
            status="PASS",
            details=f"Setup reached stage '{stage_name}' (≥ required '{min_name}').",
            is_mandatory=hard,
            deduction=0,
            evidence_refs=evidence,
        )

    min_name = _PHX_STAGE_ORDER[min_required]
    return RuleCheck(
        id="GR-P01",
        name="PHX Sequence Completeness",
        status="FAIL" if hard else "WARN",
        details=f"Setup at '{stage_name}' (idx {stage_idx}) — must reach '{min_name}' (idx {min_required}).",
        is_mandatory=hard,
        deduction=cfg["score_deduction_fail"] if hard else cfg["score_deduction_warn"],
        evidence_refs=evidence,
    )


def _rule_displacement_quality(setup_data: Dict, cfg: Dict) -> RuleCheck:
    """GR-D01: Are ≥ displacement_min_candle_ratio of displacement candles directional?"""
    hard = cfg.get("displacement_quality_hard_block", False)
    min_ratio = float(cfg["displacement_min_candle_ratio"])

    # Read from metadata if detector supplies it; else infer from setup stage
    displace_meta = setup_data.get("displacement_meta", {})
    total = displace_meta.get("total_candles", 3)
    directional = displace_meta.get("directional_candles", None)

    # Fallback: if setup is at DISPLACE or beyond and no metadata, assume 2/3
    if directional is None:
        stage_name = setup_data.get("stage", "IDLE").upper()
        stage_idx = _stage_index(stage_name)
        if stage_idx >= _stage_index("DISPLACE"):
            directional = max(2, round(min_ratio * total))  # assume passes
        else:
            directional = 0  # hasn't reached displacement yet

    ratio = directional / total if total > 0 else 0.0
    ratio_r = round(
        ratio, 2
    )  # avoid float precision issues at boundary (e.g. 0.6666... vs 0.67)
    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="displacement_directional_candles",
            value=directional,
            description=f"Out of {total}",
        ),
        EvidenceRef(ref_type="metric", key="displacement_ratio", value=ratio_r),
    ]

    if ratio_r >= min_ratio:
        return RuleCheck(
            id="GR-D01",
            name="Displacement Quality",
            status="PASS",
            details=f"{directional}/{total} displacement candles are directional ({ratio_r:.0%} ≥ {min_ratio:.0%}).",
            is_mandatory=hard,
            deduction=0,
            evidence_refs=evidence,
        )
    return RuleCheck(
        id="GR-D01",
        name="Displacement Quality",
        status="FAIL" if hard else "WARN",
        details=f"Only {directional}/{total} displacement candles are directional ({ratio_r:.0%} < {min_ratio:.0%}).",
        is_mandatory=hard,
        deduction=cfg["score_deduction_fail"] if hard else cfg["score_deduction_warn"],
        evidence_refs=evidence,
    )


def _rule_setup_score(setup_data: Dict, cfg: Dict) -> RuleCheck:
    """GR-SC01: Is the setup score ≥ min_setup_score?"""
    hard = cfg.get("setup_score_hard_block", False)
    minimum = int(cfg["min_setup_score"])
    score = setup_data.get("score")
    if score is None:
        # Fallback: map PHX stage to score
        stage_name = setup_data.get("stage", "IDLE").upper()
        stage_map = {
            "IDLE": 0,
            "BIAS": 10,
            "SWEEP": 30,
            "DISPLACE": 50,
            "CHOCH_BOS": 70,
            "RETEST": 85,
            "TRIGGER": 100,
        }
        score = stage_map.get(stage_name, 0)

    score = int(score)
    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="setup_score",
            value=score,
            description=f"Min required: {minimum}",
        )
    ]

    if score >= minimum:
        return RuleCheck(
            id="GR-SC01",
            name="Minimum Setup Score",
            status="PASS",
            details=f"Setup score {score} ≥ minimum {minimum}.",
            is_mandatory=hard,
            deduction=0,
            evidence_refs=evidence,
        )
    return RuleCheck(
        id="GR-SC01",
        name="Minimum Setup Score",
        status="FAIL" if hard else "WARN",
        details=f"Setup score {score} < minimum {minimum}.",
        is_mandatory=hard,
        deduction=cfg["score_deduction_fail"] if hard else cfg["score_deduction_warn"],
        evidence_refs=evidence,
    )


# Removed _rule_risk_state -> Migrated to LockoutEngine

def _rule_duplicate_signal(
    setup_data: Dict, cfg: Dict, db: Session, now_nairobi: datetime
) -> RuleCheck:
    """GR-U01: Warn if identical setup (pair + direction + stage) seen recently."""
    hard = cfg.get("duplicate_suppression_hard_block", False)
    window_mins = int(cfg["duplicate_suppression_window_minutes"])
    pair = setup_data.get("asset_pair", "")
    direction = (
        "BUY"
        if float(setup_data.get("take_profit", 0))
        > float(setup_data.get("entry_price", 1))
        else "SELL"
    )
    stage = setup_data.get("stage", setup_data.get("strategy_name", "UNKNOWN")).upper()

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_mins)
    recent_tickets = (
        db.query(OrderTicket)
        .filter(
            OrderTicket.pair == pair,
            OrderTicket.direction == direction,
            OrderTicket.created_at >= cutoff,
        )
        .count()
    )

    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="recent_same_direction_tickets",
            value=recent_tickets,
            description=f"Last {window_mins}min",
        ),
        EvidenceRef(
            ref_type="metric",
            key="pair_direction_stage",
            value=f"{pair}/{direction}/{stage}",
        ),
    ]

    if recent_tickets > 0:
        return RuleCheck(
            id="GR-U01",
            name="Duplicate Signal Suppression",
            status="FAIL" if hard else "WARN",
            details=f"Found {recent_tickets} ticket(s) for {pair} {direction} in the last {window_mins}min without meaningful state change.",
            is_mandatory=hard,
            deduction=cfg["score_deduction_fail"]
            if hard
            else cfg["score_deduction_warn"],
            evidence_refs=evidence,
        )
    return RuleCheck(
        id="GR-U01",
        name="Duplicate Signal Suppression",
        status="PASS",
        details=f"No recent duplicate signal for {pair} {direction}/{stage}.",
        is_mandatory=hard,
        deduction=0,
        evidence_refs=evidence,
    )


def _rule_quote_staleness(
    setup_data: Dict, cfg: Dict, db: Session, now_utc: datetime
) -> RuleCheck:
    """GR-Q01: Check if the live quotes for this pair are unacceptably stale."""
    from shared.database.models import QuoteStaleLog
    from sqlalchemy import func

    limit = float(cfg.get("quote_staleness_limit_seconds", 15.0))
    pair = setup_data.get("asset_pair", "")
    hard = True  # Staleness is inherently a life-safety issue, fail-closed.

    cutoff = now_utc - timedelta(minutes=2)

    # Count records first — zero records means bridge is offline, not "fresh"
    log_count = (
        db.query(func.count(QuoteStaleLog.id))
        .filter(QuoteStaleLog.symbol == pair, QuoteStaleLog.created_at >= cutoff)
        .scalar()
        or 0
    )

    if log_count == 0:
        # FAIL-CLOSED: no telemetry in the last 2 min → bridge may be offline
        return RuleCheck(
            id="GR-Q01",
            name="Quote Staleness Check",
            status="FAIL",
            details=(
                f"FAIL-CLOSED: No QuoteStaleLog records for '{pair}' in the last 2 min. "
                "Bridge may be offline or never connected."
            ),
            is_mandatory=hard,
            deduction=cfg.get("score_deduction_fail", 20),
            evidence_refs=[
                EvidenceRef(
                    ref_type="metric",
                    key="log_count_2min",
                    value=0,
                    description="No stale-log records found in 2-min lookback window",
                )
            ],
        )

    # Records exist — evaluate max observed staleness
    max_stale = (
        db.query(func.max(QuoteStaleLog.stale_duration_seconds))
        .filter(QuoteStaleLog.symbol == pair, QuoteStaleLog.created_at >= cutoff)
        .scalar()
    )
    max_stale = float(max_stale) if max_stale is not None else 0.0

    evidence = [
        EvidenceRef(
            ref_type="metric",
            key="max_quote_stale_seconds",
            value=round(max_stale, 1),
            description=f"Max staleness in last 2 mins ({log_count} records)",
        )
    ]

    if max_stale > limit:
        return RuleCheck(
            id="GR-Q01",
            name="Quote Staleness Check",
            status="FAIL",
            details=f"Max quote staleness {max_stale:.1f}s > limit {limit}s. Broker feeds may be lagging/offline.",
            is_mandatory=hard,
            deduction=cfg.get("score_deduction_fail", 20),
            evidence_refs=evidence,
        )

    return RuleCheck(
        id="GR-Q01",
        name="Quote Staleness Check",
        status="PASS",
        details=f"Quotes are fresh (max staleness {max_stale:.1f}s ≤ {limit}s, {log_count} records).",
        is_mandatory=hard,
        deduction=0,
        evidence_refs=evidence,
    )


# ──────────────────────────────────────────────────────────────────────────
# Main Engine
# ──────────────────────────────────────────────────────────────────────────


class GuardrailsEngine:
    def __init__(self, config_path: str = _DEFAULT_CONFIG_PATH):
        self.cfg = load_config(config_path)
        logger.info(f"GuardrailsEngine v{GUARDRAILS_VERSION} initialised.")

    def evaluate(
        self,
        setup_data: Dict[str, Any],
        context_data: Optional[Dict[str, Any]] = None,
        account_state: Optional[Dict[str, Any]] = None,
        db: Optional[Session] = None,
        now_nairobi: Optional[datetime] = None,
        setup_packet_id: Optional[int] = None,
        config_override: Optional[Dict[str, Any]] = None,
        policy_hash: Optional[str] = None,
    ) -> GuardrailsResult:
        """
        Run all 7 guardrail rules against a setup.
        Args:
            setup_data: dict from TechnicalSetupPacket.data or equivalent
            context_data: dict from MarketContextPacket.data (events, no_trade_windows)
            account_state: dict {consecutive_losses, daily_loss, account_balance}
            db: SQLAlchemy session (used for duplicate check)
            now_nairobi: override for deterministic testing (Africa/Nairobi timezone)
            setup_packet_id: FK to the Packet table row
            config_override: Optional dynamic configuration dict (from PolicyRouter)
        """
        if now_nairobi is None:
            now_nairobi = get_nairobi_time()
        context_data = context_data or {}
        account_state = account_state or {
            "consecutive_losses": 0,
            "daily_loss": 0.0,
            "account_balance": 10000.0,
        }

        # Use effective config: override > self.cfg
        effective_cfg = self.cfg.copy()
        if config_override:
            effective_cfg.update(config_override)

        checks: List[RuleCheck] = []

        # GR-E01 End of Day Gap (Broker Spread Widening)
        checks.append(_rule_eod_gap(now_nairobi, effective_cfg))

        # GR-P01 PHX sequence completeness
        checks.append(_rule_phx_sequence(setup_data, effective_cfg))

        # GR-D01 Displacement quality
        checks.append(_rule_displacement_quality(setup_data, effective_cfg))

        # GR-SC01 Setup score
        checks.append(_rule_setup_score(setup_data, effective_cfg))

        # GR-U01 Duplicate signal (requires DB)
        # GR-Q01 Quote staleness (requires DB)
        if db is not None:
            checks.append(
                _rule_duplicate_signal(setup_data, effective_cfg, db, now_nairobi)
            )
            # Quote staleness needs UTC time
            now_utc = now_nairobi.astimezone(timezone.utc)
            checks.append(_rule_quote_staleness(setup_data, effective_cfg, db, now_utc))
        else:
            checks.append(
                RuleCheck(
                    id="GR-U01",
                    name="Duplicate Signal Suppression",
                    status="WARN",
                    details="DB not available for duplicate check — skipping.",
                    is_mandatory=False,
                    deduction=effective_cfg["score_deduction_warn"],
                )
            )
            checks.append(
                RuleCheck(
                    id="GR-Q01",
                    name="Quote Staleness Check",
                    status="WARN",
                    details="DB not available for staleness check — skipping.",
                    is_mandatory=False,
                    deduction=effective_cfg["score_deduction_warn"],
                )
            )

        # ── Score computation ──────────────────────────────────────────
        deductions = sum(c.deduction for c in checks)
        score = max(0, 100 - deductions)

        # ── Hard block: any FAIL on a mandatory rule ───────────────────
        hard_block = any(c.status == "FAIL" and c.is_mandatory for c in checks)
        primary_reason: Optional[str] = None
        if hard_block:
            first_fail = next(
                c for c in checks if c.status == "FAIL" and c.is_mandatory
            )
            primary_reason = (
                f"[{first_fail.id}] {first_fail.name}: {first_fail.details}"
            )

        pair = setup_data.get("asset_pair", "UNKNOWN")
        result = GuardrailsResult(
            guardrails_version=GUARDRAILS_VERSION,
            setup_packet_id=setup_packet_id,
            pair=pair,
            created_at=now_nairobi,
            rule_checks=checks,
            discipline_score=score,
            hard_block=hard_block,
            primary_block_reason=primary_reason,
            policy_name=effective_cfg.get("policy_name"),
            policy_hash=policy_hash,
        )
        logger.info(
            f"Guardrails [{pair}]: score={score} hard_block={hard_block} "
            f"P:{result.pass_count} W:{result.warn_count} F:{result.fail_count}"
        )
        return result

    def persist(self, result: GuardrailsResult, db: Session) -> GuardrailsLog:
        """Persist a GuardrailsResult to the DB.  Returns the created row."""
        record = GuardrailsLog(
            setup_packet_id=result.setup_packet_id,
            pair=result.pair,
            discipline_score=result.discipline_score,
            hard_block=result.hard_block,
            primary_block_reason=result.primary_block_reason,
            guardrails_version=result.guardrails_version,
            result_json=result.model_dump(mode="json"),
            policy_name=result.policy_name,
            policy_hash=result.policy_hash,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
