"""
services/research/tests/test_pipeline_parity.py
Verifies that the research simulator matches the live production pipeline
in terms of which components it invokes and how tickets/scores are generated.

Tests:
  1. Pipeline parity — PHXDetector, real lot sizing, real score are used
  2. Outcome simulator edge cases (BE short, TP2 long/short, pending)
  3. Calibration sanity — recommendations respond correctly to metric changes
"""

import os
import csv
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from shared.types.packets import Candle
from shared.types.research import (
    SimulatedTrade,
    CounterfactualConfig,
    ResearchRunResult,
    ResearchMetrics,
)
from shared.logic.phx_detector import PHXDetector, PHXStage
from services.research.simulator import (
    _calc_lot_size,
    _emit_setup_from_detector,
    _get_research_context,
    run_replay,
)
from services.research.outcome import simulate_outcome
from services.research.calibration import analyze_variant, generate_calibration_report


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ts(offset_hours: float = 0.0) -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=offset_hours)


def _candle(open_, close, h=None, low_val=None, t=None, vol=1000.0) -> Candle:
    high = h if h is not None else max(open_, close) + 1.0
    low = low_val if low_val is not None else min(open_, close) - 1.0
    return Candle(
        timestamp=t or _ts(), open=open_, high=high, low=low, close=close, volume=vol
    )


def _make_phx_trigger_candles(base: float = 2000.0):
    """
    Construct a minimal synthetic candle sequence that drives PHXDetector to TRIGGER.
    PHX stages: IDLE → BIAS → SWEEP → DISPLACE → CHOCH_BOS → RETEST → TRIGGER
    """
    candles = []
    # IDLE → BIAS: 3 consecutive higher highs
    for i in range(3):
        candles.append(
            Candle(
                timestamp=_ts(i),
                open=base,
                high=base + i + 1,
                low=base - 1,
                close=base + i,
                volume=1000,
            )
        )
    # BIAS → SWEEP: need 10 candles history; price dips below min_low then closes above it (bullish sweep)
    # First fill to 10 candles total
    for i in range(3, 9):
        candles.append(
            Candle(
                timestamp=_ts(i),
                open=base + 2,
                high=base + 3,
                low=base + 1,
                close=base + 2,
                volume=1000,
            )
        )
    # Sweep candle: low below min of last 9, closes above it
    min_low = min(c.low for c in candles[-9:])
    sweep_candle = Candle(
        timestamp=_ts(9),
        open=min_low + 2,
        high=min_low + 5,
        low=min_low - 1,
        close=min_low + 3,
        volume=2000,
    )
    candles.append(sweep_candle)
    # SWEEP → DISPLACE: 2 of last 3 candles bullish
    candles.append(
        Candle(
            timestamp=_ts(10),
            open=base + 2,
            high=base + 6,
            low=base + 1,
            close=base + 5,
            volume=1000,
        )
    )
    candles.append(
        Candle(
            timestamp=_ts(11),
            open=base + 4,
            high=base + 8,
            low=base + 3,
            close=base + 7,
            volume=1000,
        )
    )
    candles.append(
        Candle(
            timestamp=_ts(12),
            open=base + 6,
            high=base + 10,
            low=base + 5,
            close=base + 9,
            volume=1000,
        )
    )
    # DISPLACE → CHOCH_BOS: close > sweep_high_low
    choch_candle = Candle(
        timestamp=_ts(13),
        open=sweep_candle.high - 1,
        high=sweep_candle.high + 5,
        low=sweep_candle.high - 2,
        close=sweep_candle.high + 3,
        volume=1000,
    )
    candles.append(choch_candle)
    # CHOCH_BOS → RETEST: low <= choch_level
    choch_level = sweep_candle.high
    retest_candle = Candle(
        timestamp=_ts(14),
        open=choch_level + 1,
        high=choch_level + 2,
        low=choch_level - 0.5,
        close=choch_level + 0.5,
        volume=800,
    )
    candles.append(retest_candle)
    # RETEST → TRIGGER: bullish close
    trigger_candle = Candle(
        timestamp=_ts(15),
        open=choch_level,
        high=choch_level + 4,
        low=choch_level - 1,
        close=choch_level + 3,
        volume=1200,
    )
    candles.append(trigger_candle)
    return candles, trigger_candle


# ── Pipeline Parity Tests ─────────────────────────────────────────────────────


class TestPipelineParity:
    def test_phx_detector_reaches_trigger(self):
        """Verify the synthetic candle sequence exercises all PHX stages."""
        detector = PHXDetector("XAUUSD")
        candles, trigger = _make_phx_trigger_candles()
        for c in candles:
            detector.update(c)
        assert detector.stage == PHXStage.TRIGGER

    def test_emit_setup_from_real_detector(self):
        """Setup emitted from real PHX detector has correct structure."""
        detector = PHXDetector("XAUUSD")
        candles, trigger = _make_phx_trigger_candles()
        for c in candles:
            detector.update(c)
        setup = _emit_setup_from_detector(detector, trigger, "H1")
        assert setup is not None
        assert setup.strategy_name in ("PHX_BULL", "PHX_BEAR")
        assert setup.asset_pair == "XAUUSD"
        assert setup.entry_price > 0
        assert setup.stop_loss > 0
        # Bullish: TP must be above entry
        assert setup.take_profit > setup.entry_price

    def test_emit_setup_returns_none_when_not_trigger(self):
        """No setup should be emitted for non-TRIGGER stages."""
        detector = PHXDetector("XAUUSD")
        # Only feed 2 candles — will be IDLE
        candle = _candle(2000, 2001, t=_ts(0))
        detector.update(candle)
        result = _emit_setup_from_detector(detector, candle, "H1")
        assert result is None

    def test_detector_score_is_not_hardcoded(self):
        """Score must come from PHX stage, not a hard-coded 85."""
        detector = PHXDetector("XAUUSD")
        candles, _ = _make_phx_trigger_candles()
        for c in candles:
            detector.update(c)
        score = detector.get_score()
        assert score == 100  # TRIGGER stage

    def test_lot_sizing_parity_xauusd(self):
        """_calc_lot_size must match trading_logic.py formula for XAUUSD."""
        # Risk $100, dist $10, factor 100 → 0.1 lots
        lot = _calc_lot_size(entry=2000.0, sl=1990.0, pair="XAUUSD", risk_usd=100.0)
        assert lot == 0.10

    def test_lot_sizing_parity_gbpjpy(self):
        """GBPJPY uses 100_000 factor."""
        # Risk $100, dist 1.0, factor 100000 → 0.001 but floor is 0.01
        lot = _calc_lot_size(entry=190.0, sl=189.0, pair="GBPJPY", risk_usd=100.0)
        assert lot == 0.01

    def test_lot_sizing_zero_dist_fallback(self):
        """Zero risk distance must fall back to minimum lot."""
        lot = _calc_lot_size(entry=2000.0, sl=2000.0, pair="XAUUSD")
        assert lot == 0.01

    def test_research_context_is_deterministic(self):
        """Research context uses MockProxyProvider — same result every call."""
        ctx1 = _get_research_context()
        ctx2 = _get_research_context()
        assert ctx1["proxies"] == ctx2["proxies"]
        assert ctx1["high_impact_events"] == []

    def test_mock_proxy_no_random_in_research_context(self):
        """Confirm proxy values are stable across repeated calls."""
        ctx = _get_research_context()
        dxy = ctx["proxies"]["DXY"]["delta_pct"]
        assert dxy == 0.00, (
            "Research context must use deterministic (delta_pct=0) proxy data"
        )

    def test_reproducibility_hash_changes_on_guardrails_version(self):
        """Different guardrails versions must produce different hashes."""
        r = ResearchRunResult(
            run_id="r1",
            pair="XAUUSD",
            start_date=_ts(0),
            end_date=_ts(10),
            timeframes=["H1"],
        )
        r.generate_hash(git_commit="abc", guardrails_version="1.0")
        h1 = r.reproducibility_hash

        r.generate_hash(git_commit="abc", guardrails_version="2.0")
        h2 = r.reproducibility_hash

        assert h1 != h2

    def test_reproducibility_hash_fields_populated(self):
        """generate_hash must populate guardrails_version field."""
        r = ResearchRunResult(
            run_id="r1",
            pair="XAUUSD",
            start_date=_ts(0),
            end_date=_ts(10),
            timeframes=["H1"],
        )
        r.generate_hash(guardrails_version="3.0.1")
        assert r.guardrails_version == "3.0.1"
        assert r.reproducibility_hash != ""


# ── Outcome Simulator Edge Cases ──────────────────────────────────────────────


class TestOutcomeEdgeCases:
    def _short_trade(self):
        return SimulatedTrade(
            ticket_id="sc_1",
            pair="GBPJPY",
            direction="SHORT",
            entry_price=190.0,
            stop_loss=192.0,
            take_profit_1=186.0,
        )

    def test_short_be_trigger(self):
        """Short trade: hits -1R target (be trigger) then retraces to SL → BE."""
        trade = self._short_trade()
        candles = [
            # Risk=2.0. BE at 1R = 188.0. Candle hits 188 (triggers BE move).
            Candle(
                timestamp=_ts(0),
                open=190.0,
                high=190.5,
                low=188.0,
                close=189.0,
                volume=100,
            ),
            # Then SL hit at 192 — but SL was moved to entry (190)
            Candle(
                timestamp=_ts(1),
                open=189.0,
                high=191.0,
                low=188.5,
                close=190.5,
                volume=100,
            ),
        ]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "BE"
        assert result.realized_r == 0.0
        assert result.exit_price == 190.0

    def test_long_tp2_hit(self):
        """Trade with TP2 defined reaches TP2 and exits there."""
        trade = SimulatedTrade(
            ticket_id="tp2_1",
            pair="XAUUSD",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit_1=2040.0,
            take_profit_2=2080.0,
        )
        candles = [
            # TP1 hit — no exit because TP2 is set
            Candle(
                timestamp=_ts(0), open=2000, high=2045, low=1995, close=2040, volume=100
            ),
            # TP2 hit
            Candle(
                timestamp=_ts(1), open=2040, high=2085, low=2035, close=2075, volume=100
            ),
        ]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "WIN_TP2"
        # Risk = 20. TP2 = 2080. Gain = 80. R = 80/20 = 4.0
        assert result.realized_r == pytest.approx(4.0)
        assert result.exit_price == 2080.0

    def test_short_tp2_hit(self):
        """Short trade with TP2: exits at TP2 price."""
        trade = SimulatedTrade(
            ticket_id="stp2_1",
            pair="GBPJPY",
            direction="SHORT",
            entry_price=190.0,
            stop_loss=192.0,
            take_profit_1=186.0,
            take_profit_2=182.0,
        )
        candles = [
            Candle(
                timestamp=_ts(0),
                open=190.0,
                high=190.5,
                low=185.0,
                close=186.5,
                volume=100,
            ),
            Candle(
                timestamp=_ts(1),
                open=186.5,
                high=187.0,
                low=181.5,
                close=183.0,
                volume=100,
            ),
        ]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "WIN_TP2"
        # Risk = 2.0. TP2 dist = 8.0. R = 8/2 = 4.0
        assert result.realized_r == pytest.approx(4.0)
        assert result.exit_price == 182.0

    def test_tiebreaker_sl_over_tp_long(self):
        """Confirmed: conservative tie-break is LOSS when both SL and TP hit same candle."""
        trade = SimulatedTrade(
            ticket_id="tie_1",
            pair="XAUUSD",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=1980.0,
            take_profit_1=2040.0,
        )
        candles = [
            Candle(
                timestamp=_ts(0), open=2000, high=2100, low=1900, close=2050, volume=100
            )
        ]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "LOSS"
        assert result.realized_r == -1.0

    def test_tiebreaker_sl_over_tp_short(self):
        """Confirmed: conservative tie-break for SHORT is also LOSS."""
        trade = SimulatedTrade(
            ticket_id="ties_1",
            pair="GBPJPY",
            direction="SHORT",
            entry_price=190.0,
            stop_loss=192.0,
            take_profit_1=186.0,
        )
        candles = [
            Candle(
                timestamp=_ts(0),
                open=190.0,
                high=194.0,
                low=185.0,
                close=190.0,
                volume=100,
            )
        ]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "LOSS"
        assert result.realized_r == -1.0

    def test_zero_risk_distance_is_error(self):
        """Trade where SL == entry must be marked ERROR, not crashed."""
        trade = SimulatedTrade(
            ticket_id="zero_1",
            pair="XAUUSD",
            direction="LONG",
            entry_price=2000.0,
            stop_loss=2000.0,
            take_profit_1=2040.0,
        )
        candles = [_candle(2000, 2010, t=_ts(0))]
        result = simulate_outcome(trade.model_copy(), candles)
        assert result.status == "ERROR"


# ── Calibration Sanity Tests ──────────────────────────────────────────────────


class TestCalibrationSanity:
    def _metrics(self, er=0.0, dd=0.0, win=50.0, n=100):
        return ResearchMetrics(
            total_trades=n,
            executed_trades=n,
            blocked_trades=0,
            win_rate_pct=win,
            expectancy_r=er,
            max_drawdown_r=dd,
        )

    def test_high_conviction_recommendation_when_er_up(self):
        """If ER improves by > 0.05R and DD stable, expect HIGH conviction rec."""
        baseline = self._metrics(er=0.20, dd=2.0, win=50.0, n=100)
        variant = self._metrics(er=0.30, dd=1.5, win=55.0, n=95)
        rec = analyze_variant("tighter_score", variant, baseline)
        assert rec is not None
        assert rec.conviction == "HIGH"

    def test_medium_conviction_when_win_rate_up_volume_drops(self):
        """Win rate up significantly + volume cut → MEDIUM recommendation."""
        baseline = self._metrics(er=0.20, dd=2.0, win=45.0, n=100)
        variant = self._metrics(er=0.18, dd=2.0, win=55.0, n=55)  # 55% retention
        rec = analyze_variant("strict_filter", variant, baseline)
        assert rec is not None
        assert rec.conviction == "MEDIUM"

    def test_no_recommendation_when_metrics_flat(self):
        """No recommendation when variant produces no meaningful change."""
        baseline = self._metrics(er=0.20, dd=2.0, win=50.0, n=100)
        variant = self._metrics(er=0.18, dd=1.9, win=50.0, n=98)
        rec = analyze_variant("noise_variant", variant, baseline)
        assert rec is None

    def test_medium_drawdown_recommendation(self):
        """Big drawdown improvement at slight ER cost → MEDIUM recommendation."""
        baseline = self._metrics(er=0.30, dd=5.0, win=55.0, n=100)
        variant = self._metrics(er=0.22, dd=2.0, win=52.0, n=80)  # dd_delta 3.0 > 1.0
        rec = analyze_variant("risk_dampener", variant, baseline)
        assert rec is not None
        assert rec.conviction == "MEDIUM"

    def test_no_recommendation_when_baseline_empty(self):
        """analyze_variant returns None when baseline has zero executed trades."""
        baseline = self._metrics(er=0.0, dd=0.0, win=0.0, n=0)
        variant = self._metrics(er=0.5, dd=0.0, win=70.0, n=50)
        rec = analyze_variant("any_variant", variant, baseline)
        assert rec is None

    def test_calibration_report_sorts_high_before_medium(self):
        """HIGH conviction recommendations must appear before MEDIUM ones."""
        # Build two run results
        from shared.types.research import ResearchVariant

        baseline_cfg = CounterfactualConfig()
        var_cfg = CounterfactualConfig(min_setup_score=80.0)

        # Baseline result (high ER)
        base_variant = ResearchVariant(
            name="baseline",
            config=baseline_cfg,
            metrics=self._metrics(er=0.10, dd=3.0, win=45.0, n=200),
        )
        # High-confidence variant
        high_var = ResearchVariant(
            name="strict_score",
            config=var_cfg,
            metrics=self._metrics(er=0.20, dd=2.0, win=55.0, n=180),
        )
        # Medium-confidence variant
        win_var = ResearchVariant(
            name="win_filter",
            config=CounterfactualConfig(min_setup_score=90.0),
            metrics=self._metrics(er=0.09, dd=3.0, win=58.0, n=100),
        )

        result = ResearchRunResult(
            run_id="r1",
            pair="XAUUSD",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            timeframes=["H1"],
            variants={
                "baseline": base_variant,
                "strict_score": high_var,
                "win_filter": win_var,
            },
        )
        result.generate_hash()

        report = generate_calibration_report([result], baseline_name="baseline")
        assert len(report.recommendations) >= 1
        convictions = [r.conviction for r in report.recommendations]
        # HIGH must come before MEDIUM
        if "HIGH" in convictions and "MEDIUM" in convictions:
            assert convictions.index("HIGH") < convictions.index("MEDIUM")


# ── Small end-to-end integration: run_replay on synthetic CSV ─────────────────


class TestRunReplayIntegration:
    def _write_csv(self, candles, path):
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"]
            )
            writer.writeheader()
            for c in candles:
                writer.writerow(
                    {
                        "timestamp": c.timestamp.isoformat(),
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                )

    def test_run_replay_uses_phx_not_mock(self):
        """run_replay must NOT reference _mock_detector; setup stage must be PHX stage name."""
        import inspect
        import services.research.simulator as sim_mod

        src = inspect.getsource(sim_mod)
        assert "_mock_detector" not in src, (
            "simulator.py still references _mock_detector"
        )
        assert "MOCK_PHX_BULL" not in src, "simulator.py still uses mock strategy name"

    def test_run_replay_produces_result_with_hash(self):
        """Smoke test: end-to-end replay on synthetic data populates all reproducibility fields."""
        candles, _ = _make_phx_trigger_candles(base=2000.0)
        # Extend candles for outcome simulation (50 more bars)
        last_t = candles[-1].timestamp
        for i in range(1, 51):
            candles.append(
                Candle(
                    timestamp=last_t + timedelta(hours=i),
                    open=2010,
                    high=2015,
                    low=2005,
                    close=2012,
                    volume=500,
                )
            )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            csv_path = f.name

        try:
            self._write_csv(candles, csv_path)
            result = run_replay(
                csv_path=csv_path,
                pair="XAUUSD",
                timeframe="H1",
                start_date=candles[0].timestamp,
                end_date=candles[-1].timestamp,
                variants={"baseline": CounterfactualConfig()},
            )
            assert result.reproducibility_hash != ""
            assert result.run_id.startswith("res_")
            assert "baseline" in result.variants
        finally:
            os.unlink(csv_path)
