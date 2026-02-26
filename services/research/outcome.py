from typing import List, Optional
from shared.types.packets import Candle
from shared.types.research import SimulatedTrade

def simulate_outcome(
    trade: SimulatedTrade, 
    future_candles: List[Candle],
    be_trigger_r: float = 1.0
) -> SimulatedTrade:
    """
    Deterministically walk forward candle by candle to resolve the trade outcome.
    Assumes trade is already entered at `trade.entry_price`.
    """
    if trade.status == "BLOCKED":
        return trade
        
    is_long = trade.direction.upper() == "LONG"
    entry = trade.entry_price
    sl = trade.stop_loss
    tp1 = trade.take_profit_1
    tp2 = trade.take_profit_2
    
    # Calculate risk distance
    risk_dist = entry - sl if is_long else sl - entry
    if risk_dist <= 0:
        trade.status = "ERROR"
        trade.realized_r = 0.0
        return trade
        
    # Break-even trigger level
    be_level = entry + (risk_dist * be_trigger_r) if is_long else entry - (risk_dist * be_trigger_r)
    sl_moved_to_be = False
    
    for candle in future_candles:
        high = candle.high
        low = candle.low
        
        if is_long:
            # Tie breaker: if single candle hits both SL and TP, conservative assumption is SL hit first
            hit_sl = low <= sl
            hit_tp1 = high >= tp1
            hit_tp2 = tp2 is not None and high >= tp2
            
            if hit_sl and hit_tp1:
                # Assuming SL hit first in a massive wick for conservative testing
                trade.status = "BE" if sl_moved_to_be else "LOSS"
                trade.realized_r = 0.0 if sl_moved_to_be else -1.0
                trade.exit_price = sl
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_sl:
                trade.status = "BE" if sl_moved_to_be else "LOSS"
                trade.realized_r = 0.0 if sl_moved_to_be else -1.0
                trade.exit_price = sl
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_tp2:
                # Reached final target
                trade.status = "WIN_TP2"
                trade.realized_r = (tp2 - entry) / risk_dist
                trade.exit_price = tp2
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_tp1 and tp2 is None:
                # Reached final target (no TP2 defined)
                trade.status = "WIN_TP1"
                trade.realized_r = (tp1 - entry) / risk_dist
                trade.exit_price = tp1
                trade.exit_time = candle.timestamp
                return trade
                
            # Check BE trigger for the NEXT candles
            if not sl_moved_to_be and high >= be_level:
                sl_moved_to_be = True
                sl = entry
                
            # If hit TP1 but has TP2, it keeps running, but SL is already at BE via the trigger
            
        else: # SHORT
            hit_sl = high >= sl
            hit_tp1 = low <= tp1
            hit_tp2 = tp2 is not None and low <= tp2
            
            if hit_sl and hit_tp1:
                trade.status = "BE" if sl_moved_to_be else "LOSS"
                trade.realized_r = 0.0 if sl_moved_to_be else -1.0
                trade.exit_price = sl
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_sl:
                trade.status = "BE" if sl_moved_to_be else "LOSS"
                trade.realized_r = 0.0 if sl_moved_to_be else -1.0
                trade.exit_price = sl
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_tp2:
                trade.status = "WIN_TP2"
                trade.realized_r = (entry - tp2) / risk_dist
                trade.exit_price = tp2
                trade.exit_time = candle.timestamp
                return trade
                
            if hit_tp1 and tp2 is None:
                trade.status = "WIN_TP1"
                trade.realized_r = (entry - tp1) / risk_dist
                trade.exit_price = tp1
                trade.exit_time = candle.timestamp
                return trade
                
            # Check BE trigger for NEXT candles
            if not sl_moved_to_be and low <= be_level:
                sl_moved_to_be = True
                sl = entry
                
    # If we exit loop without hitting anything, trade is still running or closed at end of dataset
    trade.status = "PENDING"
    return trade
