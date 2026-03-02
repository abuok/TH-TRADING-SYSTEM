from enum import Enum, auto
from typing import List, Dict
from shared.types.packets import Candle
from datetime import datetime


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
        self.history.append(candle)
        # Process multiple transitions in one candle if possible (e.g. sweep + displacement)
        # But for V1 we keep it simple: one logic block per update.
        getattr(self, f"_process_{self.stage.name.lower()}")(candle)

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
