import pytest
import asyncio
from unittest.mock import MagicMock, patch
from services.orchestration.runner import Orchestrator
from shared.types.packets import (
    TechnicalSetupPacket,
    RiskApprovalPacket,
    MarketContextPacket,
)


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
def orchestrator(risk_config):
    orch = Orchestrator(risk_config, dry_run=True)
    orch.run_id = 999  # Mock run_id to avoid DB calls
    return orch


def test_pre_session_briefing(orchestrator):
    with patch.object(
        orchestrator.sessions, "compute_all_levels", return_value={"asia": 100}
    ):
        levels = asyncio.run(orchestrator.pre_session_briefing("BTCUSD", []))
        assert levels["asia"] == 100


def test_live_loop_dry_run(orchestrator):
    # Mock methods to avoid external dependencies
    orchestrator.get_latest_market_context = MagicMock(
        return_value=MarketContextPacket(
            schema_version="1.0.0",
            source="test",
            asset_pair="BTCUSD",
            price=50000.0,
            volume_24h=1.0,
        )
    )
    orchestrator.scan_for_setup = MagicMock(
        return_value=TechnicalSetupPacket(
            schema_version="1.0.0",
            asset_pair="BTCUSD",
            strategy_name="PHX",
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=53000.0,
            timeframe="1H",
        )
    )
    orchestrator.persist_packet = MagicMock()
    orchestrator.output_decision = MagicMock()

    asyncio.run(orchestrator.live_loop("BTCUSD"))

    # In dry-run, it should run once and stop
    assert orchestrator.scan_for_setup.called
    assert orchestrator.persist_packet.called
    assert orchestrator.output_decision.called


def test_generate_decision(orchestrator):
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="BTCUSD",
        strategy_name="PHX",
        entry_price=50000.0,
        stop_loss=49500.0,
        take_profit=52000.0,
        timeframe="1H",
    )
    approval = RiskApprovalPacket(
        schema_version="1.0.0",
        request_id="req1",
        status="ALLOW",
        is_approved=True,
        risk_score=80.0,
        max_position_size=0.1,
        rr_ratio=4.0,
        approver="RiskEngine",
        reasons=[],
    )

    decision = orchestrator.generate_decision(setup, approval, dry_run=True)
    assert decision.asset_pair == "BTCUSD"
    assert decision.action == "DRY_RUN_EXECUTE"
    assert decision.rr_ratio == 4.0
    assert decision.is_dry_run is True
