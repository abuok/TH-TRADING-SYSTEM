import pytest
from datetime import datetime, timedelta, time
import pytz
from shared.logic.phx_detector import PHXDetector, PHXStage
from shared.types.packets import Candle

@pytest.fixture
def detector():
    return PHXDetector(asset_pair="XAUUSD")

def create_candle(dt_nairobi: datetime, price: float = 2000.0) -> Candle:
    # Convert Nairobi time to UTC for the candle packet
    dt_utc = dt_nairobi.astimezone(pytz.UTC)
    return Candle(
        timestamp=dt_utc,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price + 0.5,
        volume=100
    )

def test_retest_staleness_6h(detector):
    # Move to RETEST
    detector.stage = PHXStage.RETEST
    base_time = datetime(2026, 3, 12, 12, 0, tzinfo=pytz.timezone("Africa/Nairobi"))
    detector.stage_timestamps[PHXStage.RETEST] = base_time.astimezone(pytz.UTC)
    
    # 7 hours later
    late_time = base_time + timedelta(hours=7)
    candle = create_candle(late_time)
    
    detector.update(candle)
    assert detector.stage == PHXStage.IDLE
    assert "Reset: RETEST stale (>6h)" in detector.reason_codes

def test_session_freeze_out_of_session(detector):
    # OUT_OF_SESSION for XAUUSD is 22:00 - 06:59
    oos_time = datetime(2026, 3, 12, 23, 0, tzinfo=pytz.timezone("Africa/Nairobi"))
    candle = create_candle(oos_time, price=2000.0)
    
    # Try to establish bias (3 higher highs)
    for i in range(5):
        c = create_candle(oos_time + timedelta(minutes=i), price=2000.0 + i)
        detector.update(c)
        
    assert detector.stage == PHXStage.IDLE
    assert len(detector.history) == 0  # Should not record history during freeze

def test_trigger_suppression_observe_only(detector):
    # PRE_SESSION for XAUUSD is 07:00 - 10:59 (OBSERVE only)
    pre_time = datetime(2026, 3, 12, 8, 0, tzinfo=pytz.timezone("Africa/Nairobi"))
    
    # Force state to RETEST
    detector.stage = PHXStage.RETEST
    detector.bias_direction = 1
    detector.choch_level = 1900.0
    
    # Send a candle that would trigger (close > open, bullish)
    candle = create_candle(pre_time, price=2000.0)
    detector.update(candle)
    
    assert detector.stage == PHXStage.RETEST
    assert "TRIGGER suppressed: OBSERVE-only in PRE_SESSION" in detector.reason_codes

def test_session_boundary_reset_trigger(detector):
    # Start in NY_OPEN (16:00 - 18:59)
    ny_time = datetime(2026, 3, 12, 18, 59, tzinfo=pytz.timezone("Africa/Nairobi"))
    detector.stage = PHXStage.TRIGGER
    detector.current_session_label = "NY_OPEN"
    
    # Move to POST_SESSION (19:00)
    post_time = ny_time + timedelta(minutes=2)
    candle = create_candle(post_time)
    
    detector.update(candle)
    assert detector.stage == PHXStage.IDLE
    assert "Reset: Session boundary crossed (POST_SESSION)" in detector.reason_codes

def test_retest_survival_3h_rule(detector):
    # At 13:59 (LDN_OPEN)
    boundary_time = datetime(2026, 3, 12, 13, 59, tzinfo=pytz.timezone("Africa/Nairobi"))
    detector.stage = PHXStage.RETEST
    detector.current_session_label = "LONDON_OPEN"
    
    # RETEST is 2h old (should survive)
    detector.stage_timestamps[PHXStage.RETEST] = (boundary_time - timedelta(hours=2)).astimezone(pytz.UTC)
    
    # Move to 14:01 (LONDON_MID)
    new_time = boundary_time + timedelta(minutes=2)
    candle = create_candle(new_time)
    detector.update(candle)
    assert detector.stage == PHXStage.RETEST
    
    # RETEST is 4h old (should reset)
    detector.stage_timestamps[PHXStage.RETEST] = (new_time - timedelta(hours=4)).astimezone(pytz.UTC)
    # Trigger another transition logic by sending another candle within MID session (no transition label, but handles age)
    # Actually transition logic only fires on label change. Let's force another label change.
    
    # Move to NY_OPEN (16:00)
    ny_time = datetime(2026, 3, 12, 16, 1, tzinfo=pytz.timezone("Africa/Nairobi"))
    candle = create_candle(ny_time)
    detector.update(candle)
    assert detector.stage == PHXStage.IDLE
    assert any("RETEST too old at session boundary" in r for r in detector.reason_codes)

def test_bias_invalidation_reset(detector):
    detector.stage = PHXStage.CHOCH_BOS
    detector.invalidate()
    
    assert detector.stage == PHXStage.IDLE
    assert detector.is_invalidated is True
    
    # Updates should do nothing
    candle = create_candle(datetime.now(pytz.timezone("Africa/Nairobi")))
    detector.update(candle)
    assert detector.stage == PHXStage.IDLE
    
    detector.reactivate()
    assert detector.is_invalidated is False
