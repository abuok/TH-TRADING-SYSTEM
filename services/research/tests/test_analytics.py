import pytest

from services.research.analytics import calculate_metrics
from shared.types.research import SimulatedTrade


@pytest.fixture
def fake_trades():
    return [
        SimulatedTrade(
            ticket_id="t1",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="WIN_TP1",
            realized_r=2.0,
        ),
        SimulatedTrade(
            ticket_id="t2",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="LOSS",
            realized_r=-1.0,
        ),
        SimulatedTrade(
            ticket_id="t3",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="WIN_TP1",
            realized_r=1.5,
        ),
        SimulatedTrade(
            ticket_id="t4",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="BLOCKED",
            realized_r=0.0,
        ),
        SimulatedTrade(
            ticket_id="t5",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="BE",
            realized_r=0.0,
        ),
    ]


def test_calculate_metrics_basic(fake_trades):
    m = calculate_metrics(fake_trades)

    assert m.total_trades == 5
    assert m.blocked_trades == 1
    assert m.executed_trades == 4

    # Wins: t1 (2.0), t3 (1.5) -> 2 wins out of 4 executed -> 50%
    assert m.win_rate_pct == 50.0

    # Total R = 2.0 - 1.0 + 1.5 + 0.0 = 2.5
    assert m.total_r == 2.5

    # Avg R = 2.5 / 4 = 0.625 => 0.62
    assert m.avg_r == 0.62


def test_calculate_metrics_drawdown():
    trades = [
        SimulatedTrade(
            ticket_id="d1",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="WIN_TP1",
            realized_r=2.0,
        ),
        SimulatedTrade(
            ticket_id="d2",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="LOSS",
            realized_r=-1.0,
        ),
        SimulatedTrade(
            ticket_id="d3",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="LOSS",
            realized_r=-1.0,
        ),
        SimulatedTrade(
            ticket_id="d4",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="WIN_TP1",
            realized_r=3.0,
        ),
    ]
    # Running R: [2.0, 1.0, 0.0, 3.0]
    # Peak R: [2.0, 2.0, 2.0, 3.0]
    # Drawdown: [0.0, 1.0, 2.0, 0.0] -> Max DD = 2.0

    m = calculate_metrics(trades)
    assert m.max_drawdown_r == 2.0


def test_calculate_metrics_profit_factor():
    trades = [
        SimulatedTrade(
            ticket_id="p1",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="WIN_TP1",
            realized_r=3.0,
        ),
        SimulatedTrade(
            ticket_id="p2",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="LOSS",
            realized_r=-1.0,
        ),
        SimulatedTrade(
            ticket_id="p3",
            pair="X",
            direction="LONG",
            entry_price=10,
            stop_loss=9,
            take_profit_1=12,
            status="LOSS",
            realized_r=-1.0,
        ),
    ]

    # Gross Winner R = 3.0
    # Gross Loser R = 2.0
    # PF = 3.0 / 2.0 = 1.5

    m = calculate_metrics(trades)
    assert m.profit_factor == 1.5


def test_calculate_metrics_empty():
    m = calculate_metrics([])
    assert m.total_trades == 0
    assert m.executed_trades == 0
    assert m.win_rate_pct == 0.0
