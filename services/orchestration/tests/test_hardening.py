import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from services.orchestration.runner import Orchestrator
from shared.types.packets import MarketContextPacket
import shared.database.session as db_session
from shared.database.models import KillSwitch, IncidentLog


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


def test_kill_switch_halt_all(risk_config):
    db = db_session.SessionLocal()
    # Activate global kill switch
    ks = KillSwitch(switch_type="HALT_ALL", is_active=1)
    db.add(ks)
    db.commit()

    orchestrator = Orchestrator(risk_config, dry_run=True)
    with patch("services.orchestration.runner.logger") as mock_logger:
        asyncio.run(orchestrator.live_loop("BTCUSD"))
        # Should have logged that it's halted
        assert any(
            "HALTED by kill switch" in call.args[0]
            for call in mock_logger.warning.call_args_list
        )


def test_kill_switch_halt_pair(risk_config):
    db = db_session.SessionLocal()
    # Activate pair kill switch
    ks = KillSwitch(switch_type="HALT_PAIR", target="BTCUSD", is_active=1)
    db.add(ks)
    db.commit()

    orchestrator = Orchestrator(risk_config, dry_run=True)
    with patch("services.orchestration.runner.logger") as mock_logger:
        asyncio.run(orchestrator.live_loop("BTCUSD"))
        assert any(
            "Pair BTCUSD HALTED by kill switch" in call.args[0]
            for call in mock_logger.warning.call_args_list
        )


def test_stale_packet_rejection(risk_config):
    orchestrator = Orchestrator(risk_config, dry_run=True)

    # Create a stale packet (31 seconds old, TTL is 30)
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=31)
    stale_context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=65000.0,
        volume_24h=100.0,
        timestamp=stale_time,
    )

    with patch.object(
        orchestrator, "get_latest_market_context", return_value=stale_context
    ):
        with patch("services.orchestration.runner.logger") as mock_logger:
            asyncio.run(orchestrator.live_loop("BTCUSD"))
            assert any(
                "Abandoning loop iteration" in call.args[0]
                for call in mock_logger.error.call_args_list
            )

    # Verify incident was logged to DB
    db = db_session.SessionLocal()
    incident = db.query(IncidentLog).first()
    assert incident is not None
    assert incident.error_code == "STALE_PACKET"


def test_notif_idempotency(risk_config):
    mock_notifier = MagicMock()
    orchestrator = Orchestrator(risk_config, dry_run=True, notifier=mock_notifier)

    # Trigger first notification
    detector = orchestrator.get_detector("BTCUSD")
    detector.get_score = MagicMock(return_value=60)  # Forming

    context = MarketContextPacket(
        schema_version="1.0.0",
        source="Test",
        asset_pair="BTCUSD",
        price=65000.0,
        volume_24h=100.0,
        timestamp=datetime.now(timezone.utc),
    )

    with patch.object(orchestrator, "get_latest_market_context", return_value=context):
        asyncio.run(orchestrator.live_loop("BTCUSD"))
        forming_calls = [
            call
            for call in mock_notifier.notify.call_args_list
            if "Setup Forming" in call.args[0]
        ]
        assert len(forming_calls) == 1

        # Second run with same score - should NOT notify again
        asyncio.run(orchestrator.live_loop("BTCUSD"))
        forming_calls = [
            call
            for call in mock_notifier.notify.call_args_list
            if "Setup Forming" in call.args[0]
        ]
        assert len(forming_calls) == 1

        # Third run with different score (significantly changed) - SHOULD notify
        detector.get_score.return_value = 75
        asyncio.run(orchestrator.live_loop("BTCUSD"))
        forming_calls = [
            call
            for call in mock_notifier.notify.call_args_list
            if "Setup Forming" in call.args[0]
        ]
        assert len(forming_calls) == 2
