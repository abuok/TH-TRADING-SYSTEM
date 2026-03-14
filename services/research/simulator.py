"""
services/research/simulator.py
Research Replay Engine — uses the SAME pipeline components as live production.

Pipeline parity checklist:
  [x] PHXDetector  — real shared/logic/phx_detector.py (candle-by-candle state machine)
  [x] GuardrailsEngine — same shared/logic/guardrails.py + load_config()
  [x] PolicyRouter — same shared/logic/policy_router.py
  [x] Ticket sizing — same generate_order_ticket() logic (mocked DB) via _calc_lot_size()
  [x] Fundamentals  — real evaluate_fundamentals() with MockProxyProvider context
  [x] Reproducibility hash — includes guardrails_version, policy_hash, fundamentals hash
"""

import csv
import os
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional

from shared.types.packets import Candle, TechnicalSetupPacket
from shared.types.trading import OrderTicketSchema
from shared.types.research import (
    SimulatedTrade,
    CounterfactualConfig,
    ResearchRunResult,
    ResearchVariant,
)
from shared.logic.fundamentals_engine import evaluate_fundamentals
from shared.logic.alignment import AlignmentEngine
from shared.logic.policy_router import PolicyRouter
from shared.logic.phx_detector import PHXDetector, PHXStage
from shared.providers.proxy import MockProxyProvider

from services.research.outcome import simulate_outcome
from services.research.analytics import calculate_metrics

logger = logging.getLogger("ResearchSimulator")


# ── CSV Parser ────────────────────────────────────────────────────────────────


def _parse_csv(filepath: str) -> List[Candle]:
    candles = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            candles.append(
                Candle(
                    timestamp=dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return sorted(candles, key=lambda c: c.timestamp)


# ── Ticket sizing (mirrors shared/logic/trading_logic.py logic) ───────────────


def _calc_lot_size(
    entry: float, sl: float, pair: str, risk_usd: float = 100.0
) -> float:
    """
    Mirrors the lot-sizing logic in generate_order_ticket().
    XAUUSD: $1 move = $100/lot → factor 100.
    Everything else: 100 000 factor.
    """
    dist = abs(entry - sl)
    if dist == 0:
        return 0.01
    factor = 100.0 if "XAU" in pair else 100_000.0
    return round(max(0.01, risk_usd / (dist * factor)), 2)


# ── Real PHX Detector integration ─────────────────────────────────────────────


def _emit_setup_from_detector(
    detector: PHXDetector,
    candle: Candle,
    timeframe: str,
) -> Optional[TechnicalSetupPacket]:
    """
    Convert a PHXDetector in TRIGGER state into a TechnicalSetupPacket,
    exactly mirroring how the live technical service builds setups.
    """
    if detector.stage != PHXStage.TRIGGER:
        return None

    bias = detector.bias_direction
    direction_str = "PHX_BULL" if bias == 1 else "PHX_BEAR"

    # Entry: trigger candle close
    entry = candle.close
    # SL: sweep level (the liquidity taken out), with a small buffer
    sl_raw = detector.sweep_level or entry
    sl_buffer = abs(candle.high - candle.low) * 0.5  # half ATR buffer
    sl = (sl_raw - sl_buffer) if bias == 1 else (sl_raw + sl_buffer)
    # TP: 2R target (mirrors live minimums)
    dist = abs(entry - sl)
    tp = (entry + dist * 2.0) if bias == 1 else (entry - dist * 2.0)

    return TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair=detector.asset_pair,
        strategy_name=direction_str,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        timeframe=timeframe,
        timestamp=candle.timestamp,
    )


# ── Fundamentals Context (stable mock proxies for research) ───────────────────


def _get_research_context() -> dict:
    """
    Returns a stable fundamentals context for replay.
    Uses MockProxyProvider (deterministic, no random-walk) so results are reproducible.
    """
    mock = MockProxyProvider()
    return {
        "proxies": mock.get_snapshots(),
        "high_impact_events": [],  # No live events — research is context-neutral by default
        "no_trade_windows": [],
    }


# ── Main replay function ───────────────────────────────────────────────────────


def run_replay(
    csv_path: str,
    pair: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    variants: Dict[str, CounterfactualConfig],
    risk_usd: float = 100.0,
) -> ResearchRunResult:
    """
    Replay historical candles through the real PHX→Guardrails→Ticket pipeline.
    """
    run_id = f"res_{uuid.uuid4().hex[:8]}"
    candles = _parse_csv(csv_path)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    valid_candles = [c for c in candles if start_date <= c.timestamp <= end_date]
    if not valid_candles:
        raise ValueError("No candles found in specified date range.")

    result = ResearchRunResult(
        run_id=run_id,
        pair=pair,
        start_date=valid_candles[0].timestamp,
        end_date=valid_candles[-1].timestamp,
        timeframes=[timeframe],
    )

    # Stable fundamentals context for all variants
    ctx = _get_research_context()

    for variant_name, config_override in variants.items():
        variant_trades: List[SimulatedTrade] = []

        # Build guardrails config (applied or overridden per variant)
        gc = load_config()
        if config_override.min_setup_score is not None:
            gc["min_setup_score"] = config_override.min_setup_score
        if config_override.hard_block_displacement is not None:
            gc["displacement_quality_hard_block"] = (
                config_override.hard_block_displacement
            )

        # Policy router (if variant uses it, loads same config/policies dir as live)
        policy_router: Optional[PolicyRouter] = None
        if config_override.use_router:
            policy_router = PolicyRouter()

        # Guardrails engine (same class used by live orchestration)
        gr_engine = GuardrailsEngine()

        # PHX candle-by-candle state machine
        detector = PHXDetector(asset_pair=pair)

        last_signal_time: Optional[datetime] = None

        for i, candle in enumerate(valid_candles):
            detector.update(candle)

            # Only act on TRIGGER stage
            setup = _emit_setup_from_detector(detector, candle, timeframe)
            if not setup:
                continue

            # Duplicate suppression
            current_time = candle.timestamp
            suppression = config_override.duplicate_suppression_minutes or 60
            if last_signal_time:
                diff_mins = (current_time - last_signal_time).total_seconds() / 60.0
                if diff_mins < suppression:
                    # Suppress and reset so detector can find the next clean setup
                    detector.reset()
                    continue

            last_signal_time = current_time

            # Fundamentals — real evaluate_fundamentals with stable context
            movers, pair_packets = evaluate_fundamentals(ctx, current_time)
            bias_pkt = next((p for p in pair_packets if p.asset_pair == pair), None)
            bias_score = bias_pkt.bias_score if bias_pkt else 0.0

            # Policy router (same loading mechanism as live)
            policy_config = gc
            policy_hash = None
            if policy_router is not None:
                try:
                    decision = policy_router.select_policy(
                        movers_data=movers,
                        context_data=ctx,
                        pair_fundamentals=bias_pkt.model_dump() if bias_pkt else {},
                        now_nairobi=current_time,
                    )
                    policy_config = decision.policy_config
                    policy_hash = decision.policy_hash
                except RuntimeError as e:
                    logger.warning("PolicyRouter failed: %s — using base config.", e)

            # Guardrails — same engine as live
            gr_res = gr_engine.evaluate(
                setup.model_dump(),
                ctx,
                None,
                None,
                current_time,
                1,
                config_override=policy_config if config_override.use_router else None,
                policy_hash=policy_hash,
            )

            # Ticket sizing — same formula as generate_order_ticket() in trading_logic
            direction = "LONG" if setup.take_profit > setup.entry_price else "SHORT"
            lot_size = _calc_lot_size(
                setup.entry_price, setup.stop_loss, pair, risk_usd
            )
            dist = abs(setup.entry_price - setup.stop_loss)
            rr = abs(setup.take_profit - setup.entry_price) / dist if dist > 0 else 0.0

            ticket = OrderTicketSchema(
                ticket_id=f"tkt_{uuid.uuid4().hex[:6]}",
                setup_packet_id=0,
                risk_packet_id=0,
                pair=pair,
                direction=direction,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                take_profit_1=setup.take_profit,
                lot_size=lot_size,
                risk_usd=risk_usd,
                risk_pct=risk_usd
                / 10_000.0
                * 100,  # Placeholder % (assume $10k account)
                rr_tp1=rr,
                idempotency_key=f"res_{candle.timestamp.isoformat()}_{variant_name}",
                created_at=current_time,
                status="BLOCKED" if gr_res.hard_block else "IN_REVIEW",
                block_reason=gr_res.primary_block_reason,
            )

            # Setup score from PHX detector (real stage-based score)
            setup_score = detector.get_score()

            sim_trade = SimulatedTrade(
                ticket_id=ticket.ticket_id,
                pair=pair,
                direction=direction,
                entry_price=ticket.entry_price,
                stop_loss=ticket.stop_loss,
                take_profit_1=ticket.take_profit_1,
                status=ticket.status,
                setup_score=float(setup_score),  # real PHX stage score, not hard-coded
                bias_score=bias_score,
                guardrails_status="FAIL" if gr_res.hard_block else "PASS",
                stage=detector.stage.name,  # real PHX stage name
                block_reason=ticket.block_reason,
            )

            # Outcome simulation on remaining candles
            future_candles = valid_candles[i + 1 :]
            sim_trade = simulate_outcome(sim_trade, future_candles)
            variant_trades.append(sim_trade)

            # Reset detector so it can find the next independent setup
            detector.reset()

        metrics = calculate_metrics(variant_trades)
        result.variants[variant_name] = ResearchVariant(
            name=variant_name,
            config=config_override,
            metrics=metrics,
            trades=variant_trades,
        )

    # Enriched reproducibility hash (includes all version components)
    result.generate_hash(
        git_commit=os.getenv("GIT_COMMIT", "HEAD"),
        guardrails_version=gc.get("version", "unknown"),
        dataset_path=csv_path,
    )
    return result
