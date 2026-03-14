from enum import Enum, auto
from typing import List, Dict
from shared.types.packets import Candle
from datetime import datetime
import pytz
from shared.logic.sessions import SessionEngine


class PHXStage(Enum):
    IDLE = auto()
    BIAS = auto()
    SWEEP = auto()
    DISPLACE = auto()
    CHOCH_BOS = auto()
    RETEST = auto()
    TRIGGER = auto()


class PHXDetector:
    def __init__(self, asset_pair: str):
        self.asset_pair = asset_pair
        self.reset()

    def reset(self):
        self.stage = PHXStage.IDLE
        self.bias_direction = 0  # 1 for Long, -1 for Short
        self.sweep_level = None
        self.sweep_high_low = None  # High of bullish sweep or Low of bearish sweep
        self.choch_level = None
        self.history: List[Candle] = []
        self.stage_timestamps: Dict[PHXStage, datetime] = {}
        self.reason_codes: List[str] = []
        self.current_session_label = None
        self.is_invalidated = False

    def reset_if_triggered(self) -> bool:
        """Reset the detector back to IDLE if it has reached TRIGGER.

        Call this when a ticket generated from this detector is skipped or
        expires, so the detector can detect the next valid setup on the same
        pair.  The reset is intentionally explicit (not automatic) so the
        caller controls the lifecycle.

        Returns:
            True  — a reset was performed (detector was at TRIGGER).
            False — no reset needed (detector was not yet at TRIGGER).
        """
        if self.stage == PHXStage.TRIGGER:
            self.reset()
            return True
        return False

    def get_score(self) -> int:
        """Calculate a basic setup score (0-100)."""
        score_map = {
            PHXStage.IDLE: 0,
            PHXStage.BIAS: 10,
            PHXStage.SWEEP: 30,
            PHXStage.DISPLACE: 50,
            PHXStage.CHOCH_BOS: 70,
            PHXStage.RETEST: 85,
            PHXStage.TRIGGER: 100,
        }
        return score_map.get(self.stage, 0)

    def update(self, candle: Candle):
        """Processes a new candle and advances the detector state machine."""
        if self.is_invalidated:
            return

        # Phase 3: Session State Awareness
        ts = candle.timestamp if candle.timestamp.tzinfo else candle.timestamp.replace(tzinfo=pytz.UTC)
        nairobi_tz = pytz.timezone("Africa/Nairobi")
        now_nairobi = ts.astimezone(nairobi_tz)
        
        session_label = SessionEngine.get_session_state(now_nairobi, self.asset_pair)
        
        # 1. Handle Session Transitions
        if self.current_session_label and session_label != self.current_session_label:
            self._handle_session_transition(session_label, ts)
            
        self.current_session_label = session_label

        # 2. Apply Constitutional Session Rules
        if session_label == "OUT_OF_SESSION":
            # FREEZE: Ignore ticks, no transitions.
            return
            
        # 3. Staleness Checks
        if self.stage == PHXStage.RETEST:
            retest_ts = self.stage_timestamps.get(PHXStage.RETEST)
            if retest_ts:
                # Ensure retest_ts is aware for comparison
                retest_ts_aware = retest_ts if retest_ts.tzinfo else retest_ts.replace(tzinfo=pytz.UTC)
                if (ts - retest_ts_aware).total_seconds() > 6 * 3600:
                    self.reset()
                    self.reason_codes.append("Reset: RETEST stale (>6h)")
                    return

        self.history.append(candle)
        
        # 4. OBSERVE-only mode check
        next_stage_func = getattr(self, f"_process_{self.stage.name.lower()}")
        
        # Capture stage before process to detect if we are trying to enter TRIGGER
        current_stage = self.stage
        next_stage_func(candle)
        
        if self.stage == PHXStage.TRIGGER and current_stage != PHXStage.TRIGGER:
            # Check if TRIGGER is allowed in current session
            if session_label in ["PRE_SESSION", "ASIA_SESSION", "POST_SESSION"]:
                # SUPPRESS: Revert to RETEST
                self.stage = PHXStage.RETEST
                self.reason_codes.append(f"TRIGGER suppressed: OBSERVE-only in {session_label}")

    def _handle_session_transition(self, new_label: str, ts: datetime):
        """Implements Constitutional Step 7.1: Boundary cleanup."""
        # TRIGGER resets on session transition if no ticket confirmed
        if self.stage == PHXStage.TRIGGER:
            self.reset()
            self.reason_codes.append(f"Reset: Session boundary crossed ({new_label})")
            return

        # RETEST survival rules
        if self.stage == PHXStage.RETEST:
            retest_ts = self.stage_timestamps.get(PHXStage.RETEST)
            if retest_ts:
                retest_ts_aware = retest_ts if retest_ts.tzinfo else retest_ts.replace(tzinfo=pytz.UTC)
                age_seconds = (ts - retest_ts_aware).total_seconds()
                if age_seconds > 3 * 3600:
                    self.reset()
                    self.reason_codes.append(f"Reset: RETEST too old at session boundary ({age_seconds/3600:.1f}h)")

    def invalidate(self):
        """Immediately resets and blocks the detector until a fresh bias packet arrives."""
        self.reset()
        self.is_invalidated = True
        self.reason_codes.append("Detector INVALIDATED by Bias Engine")

    def reactivate(self):
        """Clears the invalidation block."""
        self.is_invalidated = False
        self.reason_codes.append("Detector REACTIVATED")

    def _process_idle(self, candle: Candle):
        if len(self.history) < 3:
            return
        # Establish Bias: Look for 3 consecutive higher highs or lower lows
        recent = self.history[-3:]
        if all(recent[i].high > recent[i - 1].high for i in range(1, 3)):
            self.stage = PHXStage.BIAS
            self.bias_direction = 1
            self.stage_timestamps[PHXStage.BIAS] = candle.timestamp
            self.reason_codes.append("Bullish bias established")
        elif all(recent[i].low < recent[i - 1].low for i in range(1, 3)):
            self.stage = PHXStage.BIAS
            self.bias_direction = -1
            self.stage_timestamps[PHXStage.BIAS] = candle.timestamp
            self.reason_codes.append("Bearish bias established")

    def _process_bias(self, candle: Candle):
        if len(self.history) < 10:
            return
        # Look for Sweep: Price takes out a recent (5-10 candle) High/Low and reverses
        lookback = self.history[-10:-1]
        if self.bias_direction == 1:
            min_low = min(c.low for c in lookback)
            if candle.low < min_low and candle.close > min_low:
                self.stage = PHXStage.SWEEP
                self.sweep_level = min_low
                self.sweep_high_low = candle.high
                self.stage_timestamps[PHXStage.SWEEP] = candle.timestamp
                self.reason_codes.append(f"Bullish sweep of {min_low:.2f}")
        else:
            max_high = max(c.high for c in lookback)
            if candle.high > max_high and candle.close < max_high:
                self.stage = PHXStage.SWEEP
                self.sweep_level = max_high
                self.sweep_high_low = candle.low
                self.stage_timestamps[PHXStage.SWEEP] = candle.timestamp
                self.reason_codes.append(f"Bearish sweep of {max_high:.2f}")

    def _process_sweep(self, candle: Candle):
        if len(self.history) < 3:
            return
        # Look for Displacement: 2 out of 3 candles moving strongly in the trade direction
        recent = self.history[-3:]
        if self.bias_direction == 1:
            green_count = sum(1 for c in recent if c.close > c.open)
            if green_count >= 2:
                self.stage = PHXStage.DISPLACE
                self.stage_timestamps[PHXStage.DISPLACE] = candle.timestamp
                self.reason_codes.append("Bullish displacement detected")
        else:
            red_count = sum(1 for c in recent if c.close < c.open)
            if red_count >= 2:
                self.stage = PHXStage.DISPLACE
                self.stage_timestamps[PHXStage.DISPLACE] = candle.timestamp
                self.reason_codes.append("Bearish displacement detected")

    def _process_displace(self, candle: Candle):
        # Look for CHOCH/BOS: Price breaks the high/low of the sweep candle
        if self.bias_direction == 1:
            if candle.close > self.sweep_high_low:
                self.stage = PHXStage.CHOCH_BOS
                self.choch_level = self.sweep_high_low
                self.stage_timestamps[PHXStage.CHOCH_BOS] = candle.timestamp
                self.reason_codes.append(f"Bullish CHOCH above {self.choch_level:.2f}")
        else:
            if candle.close < self.sweep_high_low:
                self.stage = PHXStage.CHOCH_BOS
                self.choch_level = self.sweep_high_low
                self.stage_timestamps[PHXStage.CHOCH_BOS] = candle.timestamp
                self.reason_codes.append(f"Bearish CHOCH below {self.choch_level:.2f}")

    def _process_choch_bos(self, candle: Candle):
        # Look for Retest: Price pulls back to the CHOCH level
        if self.bias_direction == 1:
            if candle.low <= self.choch_level:
                self.stage = PHXStage.RETEST
                self.stage_timestamps[PHXStage.RETEST] = candle.timestamp
                self.reason_codes.append("Retest of CHOCH level")
        else:
            if candle.high >= self.choch_level:
                self.stage = PHXStage.RETEST
                self.stage_timestamps[PHXStage.RETEST] = candle.timestamp
                self.reason_codes.append("Retest of CHOCH level")

    def _process_retest(self, candle: Candle):
        # Look for Trigger: Candle closes in the trade direction after retest
        if self.bias_direction == 1:
            if candle.close > candle.open:
                self.stage = PHXStage.TRIGGER
                self.stage_timestamps[PHXStage.TRIGGER] = candle.timestamp
                self.reason_codes.append("Trade Triggered")
        else:
            if candle.close < candle.open:
                self.stage = PHXStage.TRIGGER
                self.stage_timestamps[PHXStage.TRIGGER] = candle.timestamp
                self.reason_codes.append("Trade Triggered")

    def _process_trigger(self, candle: Candle):
        pass
