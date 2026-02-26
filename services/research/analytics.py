from typing import List
from shared.types.research import SimulatedTrade, ResearchMetrics

def calculate_metrics(trades: List[SimulatedTrade]) -> ResearchMetrics:
    total = len(trades)
    if total == 0:
        return ResearchMetrics()
        
    executed = [t for t in trades if t.status not in ["BLOCKED", "ERROR", "PENDING"]]
    blocked = len([t for t in trades if t.status == "BLOCKED"])
    
    if not executed:
        return ResearchMetrics(total_trades=total, blocked_trades=blocked)
        
    wins = [t for t in executed if t.realized_r > 0]
    win_rate = (len(wins) / len(executed)) * 100.0
    
    total_r = sum(t.realized_r for t in executed)
    avg_r = total_r / len(executed) if executed else 0.0
    
    # Expectancy (R) = (Win% x Avg Win R) - (Loss% x Avg Loss R)
    avg_win_r = sum(t.realized_r for t in wins) / len(wins) if wins else 0.0
    losses = [t for t in executed if t.realized_r <= 0] # Includes BE for calculation purposes
    avg_loss_r = sum(t.realized_r for t in losses) / len(losses) if losses else 0.0
    win_prob = len(wins) / len(executed)
    loss_prob = len(losses) / len(executed)
    expectancy = (win_prob * avg_win_r) + (loss_prob * avg_loss_r)
    
    # Drawdown (Max consecutive R drawdown sequence)
    max_dd = 0.0
    current_dd = 0.0
    peak_r = 0.0
    running_r = 0.0
    for t in executed:
        running_r += t.realized_r
        if running_r > peak_r:
            peak_r = running_r
            current_dd = 0.0
        else:
            current_dd = peak_r - running_r
            if current_dd > max_dd:
                max_dd = current_dd
                
    # Profit Factor: (Gross Winner R) / (Gross Loser R)
    gross_wins = sum(t.realized_r for t in wins)
    gross_losses = abs(sum(t.realized_r for t in losses))
    if gross_losses == 0:
        pf = 999.0 if gross_wins > 0 else 0.0
    else:
        pf = gross_wins / gross_losses

    return ResearchMetrics(
        total_trades=total,
        executed_trades=len(executed),
        blocked_trades=blocked,
        win_rate_pct=round(win_rate, 2),
        avg_r=round(avg_r, 2),
        expectancy_r=round(expectancy, 2),
        max_drawdown_r=round(max_dd, 2),
        profit_factor=round(pf, 2),
        total_r=round(total_r, 2)
    )
