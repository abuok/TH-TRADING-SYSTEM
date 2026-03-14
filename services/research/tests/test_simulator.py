import csv
from datetime import datetime, timedelta

import pytest

from services.research.simulator import run_replay
from shared.types.research import CounterfactualConfig


# Make a temporary CSV file fixture
@pytest.fixture
def synthetic_csv(tmp_path):
    filepath = tmp_path / "test_data.csv"
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])

        start_time = datetime(2026, 1, 1, 10, 0, 0)
        base = 2000.0

        # 1. BIAS: 3 higher highs (needs 4 candles)
        for i in range(4):
            writer.writerow(
                [
                    (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                    base,
                    base + i + 1,
                    base - 1,
                    base + i,
                    1000,
                ]
            )

        # 2. History padding to 10 candles (already have 4, need 6 more)
        for i in range(4, 10):
            writer.writerow(
                [
                    (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                    base + 2,
                    base + 3,
                    base + 1,
                    base + 2,
                    1000,
                ]
            )

        # 3. SWEEP: Price takes out min low (base-1 = 1999)
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 10)).isoformat() + "Z",
                base + 2,
                base + 5,
                base - 2,  # 1998
                base + 3,
                2000,
            ]
        )

        # 4. DISPLACE: Bullish drive
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 11)).isoformat() + "Z",
                base + 2,
                base + 6,
                base + 1,
                base + 5,
                1000,
            ]
        )
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 12)).isoformat() + "Z",
                base + 4,
                base + 8,
                base + 3,
                base + 7,
                1000,
            ]
        )
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 13)).isoformat() + "Z",
                base + 6,
                base + 10,
                base + 5,
                base + 9,
                1000,
            ]
        )

        # 5. CHOCH_BOS: break sweep high (sweep candle high was base+5 = 2005)
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 14)).isoformat() + "Z",
                base + 4,
                base + 15,
                base + 3,
                base + 12,
                1000,
            ]
        )

        # 6. RETEST
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 15)).isoformat() + "Z",
                base + 12,
                base + 13,
                base + 4,
                base + 6,
                1000,
            ]
        )

        # 7. TRIGGER
        writer.writerow(
            [
                (start_time + timedelta(minutes=15 * 16)).isoformat() + "Z",
                base + 6,
                base + 10,
                base + 5,
                base + 9,
                1000,
            ]
        )

        # 8. FUTURE (WIN)
        for i in range(17, 30):
            writer.writerow(
                [
                    (start_time + timedelta(minutes=15 * i)).isoformat() + "Z",
                    base + 9,
                    base + 50,
                    base + 8,
                    base + 45,
                    1000,
                ]
            )

    return str(filepath)


def test_run_replay_integration(synthetic_csv, monkeypatch):
    from shared.providers.proxy import MockProxyProvider

    # Force Bullish Gold: SPX drop + DXY drop
    monkeypatch.setitem(MockProxyProvider.SNAPSHOTS["SPX"], "delta_pct", -0.6)
    monkeypatch.setitem(MockProxyProvider.SNAPSHOTS["DXY"], "delta_pct", -0.2)

    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 1, 2)

    variants = {
        "baseline": CounterfactualConfig(),
        "strict": CounterfactualConfig(min_setup_score=90),
    }

    res = run_replay(
        csv_path=synthetic_csv,
        pair="XAUUSD",
        timeframe="15m",
        start_date=start_date,
        end_date=end_date,
        variants=variants,
    )

    assert res.run_id.startswith("res_")
    assert res.pair == "XAUUSD"

    # Baseline checks
    baseline = res.variants["baseline"]
    assert len(baseline.trades) > 0  # At least one Mock trade triggered

    # We pumped price after the trigger, so it should have hit WIN_TP1
    winning_trades = [t for t in baseline.trades if t.status == "WIN_TP1"]
    assert len(winning_trades) > 0

    metrics = baseline.metrics
    assert metrics.win_rate_pct > 0
    assert metrics.total_r > 0
    assert metrics.profit_factor > 0
