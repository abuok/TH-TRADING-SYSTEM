import pytest
from datetime import datetime
from shared.types.research import SimulatedTrade
from shared.types.packets import Candle
from services.research.outcome import simulate_outcome

@pytest.fixture
def fake_trade():
    return SimulatedTrade(
        ticket_id="test_1",
        pair="XAUUSD",
        direction="LONG",
        entry_price=2000.0,
        stop_loss=1980.0,
        take_profit_1=2040.0
    )

@pytest.fixture
def short_trade():
    return SimulatedTrade(
        ticket_id="test_short_1",
        pair="GBPJPY",
        direction="SHORT",
        entry_price=180.0,
        stop_loss=182.0,
        take_profit_1=176.0,
    )

def test_long_tp1_hit(fake_trade):
    # Risk distance is 20 points
    # TP1 is 40 points (2R)
    candles = [
        Candle(timestamp=datetime.now(), open=2000, high=2010, low=1995, close=2005, volume=100),
        Candle(timestamp=datetime.now(), open=2005, high=2045, low=2000, close=2040, volume=100) # Hits TP1
    ]
    
    result = simulate_outcome(fake_trade.model_copy(), candles)
    assert result.status == "WIN_TP1"
    assert result.realized_r == 2.0
    assert result.exit_price == 2040.0

def test_short_sl_hit(short_trade):
    # Risk distance is 2.0
    # Stop loss is at 182.0
    candles = [
        Candle(timestamp=datetime.now(), open=180.0, high=181.0, low=179.0, close=180.5, volume=100),
        Candle(timestamp=datetime.now(), open=180.5, high=182.5, low=179.0, close=181.0, volume=100) # Hits SL
    ]
    
    result = simulate_outcome(short_trade.model_copy(), candles)
    assert result.status == "LOSS"
    assert result.realized_r == -1.0
    assert result.exit_price == 182.0

def test_tiebreaker_sl_over_tp(fake_trade):
    # Candle hits both SL and TP in the same bar, assume SL first conservatism
    candles = [
        Candle(timestamp=datetime.now(), open=2000, high=2100, low=1900, close=2050, volume=100)
    ]
    
    result = simulate_outcome(fake_trade.model_copy(), candles)
    assert result.status == "LOSS"
    assert result.realized_r == -1.0
    assert result.exit_price == 1980.0

def test_long_be_trigger(fake_trade):
    # Risk is 20. BE trigger is at 1R (2020)
    candles = [
        # Reaches 2025 (moves SL to 2000)
        Candle(timestamp=datetime.now(), open=2000, high=2025, low=2000, close=2015, volume=100),
        # Dips to 1990 (Hits the new BE Stop Loss, but not the original 1980 SL)
        Candle(timestamp=datetime.now(), open=2015, high=2020, low=1990, close=1995, volume=100)
    ]
    
    result = simulate_outcome(fake_trade.model_copy(), candles)
    assert result.status == "BE"
    assert result.realized_r == 0.0
    assert result.exit_price == 2000.0 # BE exit

def test_pending_trade_never_resolves(fake_trade):
    # Ranges, never hitting TP or SL
    candles = [
        Candle(timestamp=datetime.now(), open=2000, high=2010, low=1990, close=2005, volume=100),
    ]
    
    result = simulate_outcome(fake_trade.model_copy(), candles)
    assert result.status == "PENDING"
    assert result.realized_r == 0.0 
    assert result.exit_price is None

def test_blocked_trades_ignored(fake_trade):
    fake_trade.status = "BLOCKED"
    candles = [Candle(timestamp=datetime.now(), open=2000, high=2100, low=1000, close=2000, volume=100)]
    result = simulate_outcome(fake_trade, candles)
    assert result.status == "BLOCKED"
