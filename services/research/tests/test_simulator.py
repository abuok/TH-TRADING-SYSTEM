import pytest
import os
import csv
from datetime import datetime, timedelta
from shared.types.research import CounterfactualConfig
from services.research.simulator import run_replay

# Make a temporary CSV file fixture
@pytest.fixture
def synthetic_csv(tmp_path):
    filepath = tmp_path / "test_data.csv"
    with open(filepath, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        
        start_time = datetime(2026, 1, 1, 10, 0, 0)
        
        # We need at least 50 candles for the sliding window
        # Let's mock a sequence where the last 3 candles trigger a LONG setup
        base_price = 100.0
        for i in range(50):
            writer.writerow([
                (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                base_price, base_price + 2, base_price - 2, base_price + 0.5, 100
            ])
            # slight upward drift
            base_price += 0.1
            
        # The trigger candles (3 consecutive bullish drives)
        for i in range(50, 53):
            writer.writerow([
                (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                base_price, base_price + 3, base_price, base_price + 2, 200
            ])
            base_price += 2
            
        # The future candles (that will immediately hit TP)
        # Entry will be around 111.0, TP will be heavily above.
        # We'll just pump the price so it hits TP to test WIN resolution.
        for i in range(53, 55):
            writer.writerow([
                (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                base_price, base_price + 20, base_price, base_price + 15, 200
            ])
            base_price += 15
            
    return str(filepath)

def test_run_replay_integration(synthetic_csv):
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 1, 2)
    
    variants = {
        "baseline": CounterfactualConfig(),
        "strict": CounterfactualConfig(min_setup_score=90)
    }
    
    res = run_replay(
        csv_path=synthetic_csv,
        pair="XAUUSD",
        timeframe="15m",
        start_date=start_date,
        end_date=end_date,
        variants=variants
    )
    
    assert res.run_id.startswith("res_")
    assert res.pair == "XAUUSD"
    
    # Baseline checks
    baseline = res.variants["baseline"]
    assert len(baseline.trades) > 0 # At least one Mock trade triggered
    
    # We pumped price after the trigger, so it should have hit WIN_TP1
    winning_trades = [t for t in baseline.trades if t.status == "WIN_TP1"]
    assert len(winning_trades) > 0
    
    metrics = baseline.metrics
    assert metrics.win_rate_pct > 0
    assert metrics.total_r > 0
    assert metrics.profit_factor > 0
