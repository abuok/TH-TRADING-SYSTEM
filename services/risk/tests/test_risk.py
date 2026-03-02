import pytest
from datetime import datetime, timezone, timedelta
from shared.logic.risk import RiskEngine
from shared.types.packets import TechnicalSetupPacket, MarketContextPacket


@pytest.fixture
def risk_config():
    return {
        "max_daily_loss": 30.0,
        "max_total_loss": 100.0,
        "max_consecutive_losses": 2,
        "min_rr_threshold": 2.0,
        "lot_size_limit": 0.1,
        "account_balance": 1000.0,
    }


@pytest.fixture
def engine(risk_config):
    return RiskEngine(risk_config)


def test_risk_eval_allow(engine):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="BTCUSD",
        strategy_name="PHX",
        entry_price=60000.0,
        stop_loss=59000.0,  # $1000 risk
        take_profit=63000.0,  # $3000 reward -> 3.0 RR
        timeframe="1H",
    )
    context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=60000.0,
        volume_24h=100.0,
    )
    account_state = {"daily_loss": 0.0, "total_loss": 0.0, "consecutive_losses": 0}

    approval = engine.evaluate(setup, context, account_state)
    assert approval.status == "ALLOW"
    assert approval.is_approved is True
    assert approval.rr_ratio == 3.0


def test_risk_eval_block_low_rr(engine):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="BTCUSD",
        strategy_name="PHX",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=61000.0,  # 1.0 RR
        timeframe="1H",
    )
    context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=60000.0,
        volume_24h=100.0,
    )
    account_state = {"daily_loss": 0.0, "total_loss": 0.0, "consecutive_losses": 0}

    approval = engine.evaluate(setup, context, account_state)
    assert approval.status == "BLOCK"
    assert any("RR Ratio" in r for r in approval.reasons)


def test_risk_eval_block_daily_loss(engine):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="BTCUSD",
        strategy_name="PHX",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=63000.0,
        timeframe="1H",
    )
    context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=60000.0,
        volume_24h=100.0,
    )
    account_state = {"daily_loss": 35.0, "total_loss": 35.0, "consecutive_losses": 0}

    approval = engine.evaluate(setup, context, account_state)
    assert approval.status == "BLOCK"
    assert any("Daily loss limit" in r for r in approval.reasons)


def test_risk_eval_block_event_window(engine):
    now = datetime.now(timezone.utc)
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="BTCUSD",
        strategy_name="PHX",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=63000.0,
        timeframe="1H",
        timestamp=now,
    )
    context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=60000.0,
        volume_24h=100.0,
        no_trade_windows=[
            {
                "start": (now - timedelta(minutes=5)).isoformat(),
                "end": (now + timedelta(minutes=5)).isoformat(),
            }
        ],
    )

    account_state = {"daily_loss": 0.0, "total_loss": 0.0, "consecutive_losses": 0}
    approval = engine.evaluate(setup, context, account_state)
    assert approval.status == "BLOCK"
    assert any("economic event window" in r for r in approval.reasons)
