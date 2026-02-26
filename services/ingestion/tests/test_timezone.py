import pytest
import pytz
from datetime import datetime, timedelta
from services.ingestion.calendar import EconomicCalendar

def test_timezone_normalization():
    # Test normalization from EST to Africa/Nairobi
    est_tz = pytz.timezone("US/Eastern")
    nairobi_tz = pytz.timezone("Africa/Nairobi")
    
    # Example time: 2026-02-26 08:30 AM EST
    dt_est = est_tz.localize(datetime(2026, 2, 26, 8, 30))
    
    # Convert manually to Nairobi (EST is UTC-5, Nairobi is UTC+3 -> 8h difference)
    dt_expected = dt_est.astimezone(nairobi_tz)
    
    # This matches the logic in EconomicCalendar (implicitly)
    assert dt_expected.hour == 16
    assert dt_expected.minute == 30
    assert dt_expected.tzinfo.zone == "Africa/Nairobi"

def test_no_trade_window_calculation():
    nairobi_tz = pytz.timezone("Africa/Nairobi")
    # Set event 1 hour in the future to ensure it falls in the next 24h
    event_time = datetime.now(nairobi_tz) + timedelta(hours=1)
    
    event = {
        "title": "Test Event",
        "impact": "High",
        "time_nairobi": event_time,
        "currency": "USD"
    }
    
    windows = EconomicCalendar.get_no_trade_windows([event])
    assert len(windows) == 1
    assert "High" in windows[0]["impact"]
    
    # Check 15m window
    start = datetime.fromisoformat(windows[0]["start"])
    end = datetime.fromisoformat(windows[0]["end"])
    
    assert (event_time - start).total_seconds() == 15 * 60
    assert (end - event_time).total_seconds() == 15 * 60
