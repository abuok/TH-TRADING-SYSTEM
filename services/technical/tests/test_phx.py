from datetime import datetime, timedelta
import pytz
from shared.types.packets import Candle
from shared.logic.phx_detector import PHXDetector, PHXStage


def create_candle(
    price: float, is_bullish: bool = True, timestamp: datetime = None
) -> Candle:
    if timestamp is None:
        timestamp = datetime.now()

    body = 1.0
    if is_bullish:
        open_p = price - body / 2
        close_p = price + body / 2
        high = close_p + 0.2
        low = open_p - 0.2
    else:
        open_p = price + body / 2
        close_p = price - body / 2
        high = open_p + 0.2
        low = close_p - 0.2

    return Candle(
        timestamp=timestamp,
        open=open_p,
        high=high,
        low=low,
        close=close_p,
        volume=100.0,
    )


def test_phx_bullish_progression():
    detector = PHXDetector("BTCUSD")
    # Use a fixed time in LONDON_OPEN (11:00 EAT) to ensure session gating doesn't block transitions
    nairobi_tz = pytz.timezone("Africa/Nairobi")
    start_time = datetime(2026, 3, 3, 11, 0, tzinfo=nairobi_tz)
    
    # 1. Initialization + Bias (3 higher highs)
    # We need at least 10 candles for sweep lookback
    prices = [95, 96, 97, 98, 99, 100, 101, 102, 103, 104]
    for i, p in enumerate(prices):
        detector.update(create_candle(p, True, start_time + timedelta(hours=i)))

    assert detector.stage == PHXStage.BIAS
    assert detector.bias_direction == 1

    # 2. Sweep (Take out a recent low)
    # Recent lows in the last 10: [95, 96, 97, 98, 99, 100, 101, 102, 103, 104]
    # min_low is 95.
    sweep_candle = Candle(
        timestamp=start_time + timedelta(hours=11),
        open=104,
        high=105,
        low=94.5,  # Sweeps 95
        close=95.5,  # Closes above 95
        volume=200,
    )
    detector.update(sweep_candle)
    assert detector.stage == PHXStage.SWEEP

    # 3. Displace (2/3 strong green)
    detector.update(create_candle(105, True, start_time + timedelta(hours=12)))
    assert detector.stage == PHXStage.DISPLACE

    # 4. CHOCH (Break sweep high 105)
    choch_candle = Candle(
        timestamp=start_time + timedelta(hours=13),
        open=106,
        high=108,
        low=105.5,
        close=107.5,  # Break 105
        volume=150,
    )
    detector.update(choch_candle)
    assert detector.stage == PHXStage.CHOCH_BOS

    # 5. Retest (Pull back to 105)
    retest_candle = Candle(
        timestamp=start_time + timedelta(hours=14),
        open=107.5,
        high=107.5,
        low=104.5,  # Retest 105
        close=106,
        volume=120,
    )
    detector.update(retest_candle)
    assert detector.stage == PHXStage.RETEST

    # 6. Trigger (Green candle)
    detector.update(create_candle(107, True, start_time + timedelta(hours=15)))
    assert detector.stage == PHXStage.TRIGGER
    assert detector.get_score() == 100


def test_phx_reset():
    detector = PHXDetector("BTCUSD")
    detector.stage = PHXStage.TRIGGER
    detector.reset()
    assert detector.stage == PHXStage.IDLE
    assert detector.bias_direction == 0
