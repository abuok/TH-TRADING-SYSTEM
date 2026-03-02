import pytest
import asyncio
from unittest.mock import MagicMock
from shared.logic.notifications import NotificationService
from services.orchestration.runner import Orchestrator
from shared.types.packets import (
    TechnicalSetupPacket,
    RiskApprovalPacket,
    MarketContextPacket,
)


@pytest.fixture
def mock_notifier():
    notifier = MagicMock(spec=NotificationService)
    return notifier


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


def test_orchestrator_notifications(risk_config, mock_notifier):
    orchestrator = Orchestrator(risk_config, dry_run=True, notifier=mock_notifier)
    orchestrator.run_id = 999  # Mock run_id

    # Mock methods to trigger setup and risk scenarios
    orchestrator.get_latest_market_context = MagicMock(
        return_value=MarketContextPacket(
            schema_version="1.0.0",
            source="test",
            asset_pair="EURUSD",
            price=1.1,
            volume_24h=1.0,
        )
    )

    # Mock detector score for "forming" notification
    mock_detector = MagicMock()
    mock_detector.get_score.return_value = 60.0
    orchestrator.detectors["EURUSD"] = mock_detector

    # Mock scan_for_setup to return a setup
    setup = TechnicalSetupPacket(
        schema_version="1.0.0",
        asset_pair="EURUSD",
        strategy_name="PHX",
        entry_price=1.1,
        stop_loss=1.09,
        take_profit=1.15,
        timeframe="1H",
    )
    orchestrator.scan_for_setup = MagicMock(return_value=setup)

    # Mock risk_engine to trigger BLOCK notification
    approval = RiskApprovalPacket(
        schema_version="1.0.0",
        request_id="req1",
        status="BLOCK",
        is_approved=False,
        risk_score=40.0,
        max_position_size=0.1,
        rr_ratio=1.5,
        approver="RiskEngine",
        reasons=["Low RR"],
    )
    orchestrator.risk_engine.evaluate = MagicMock(return_value=approval)
    orchestrator.persist_packet = MagicMock()
    orchestrator.output_decision = MagicMock()

    asyncio.run(orchestrator.live_loop("EURUSD"))

    # Verify notifications were sent
    # 1. Forming
    # 2. Execute-Ready
    # 3. Risk BLOCK
    assert mock_notifier.notify.call_count >= 3

    calls = [call.args[0] for call in mock_notifier.notify.call_args_list]
    assert any("Setup Forming" in msg for msg in calls)
    assert any("Setup Execute-Ready" in msg for msg in calls)
    assert any("Risk BLOCK" in msg for msg in calls)
