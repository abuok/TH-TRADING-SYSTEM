import asyncio
import json
import uuid
from datetime import datetime, timezone
import unittest
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.messaging.event_bus import EventBus
from shared.types.packets import (
    MarketContextPacket,
    TechnicalSetupPacket,
    RiskApprovalPacket,
    DecisionPacket,
)
from services.technical.worker import TechnicalWorker
from services.risk.worker import RiskWorker

class TestE2EWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_full_pipeline_flow(self):
        """
        Simulate the full E2E workflow: Bridge -> Technical -> Risk -> Orchestrator
        """
        bus = EventBus()
        # Ensure clean streams for the test
        test_run_id = f"test_{uuid.uuid4().hex[:8]}"

        # 1. SETUP WORKERS (Mocks for external dependencies)
        tech_worker = TechnicalWorker(pairs=["XAUUSD"])
        risk_worker = RiskWorker()
        
        # Override the event_bus client if needed, or just let them use the shared local Redis
        # We'll use mock consumers to watch what they produce.

        # Force TechnicalWorker's detector to a state where 1 more quote triggers a setup
        # For simplicity in an E2E test without waiting for 15 real candles, we'll
        # just directly construct the expected packet.

        setup_packet = TechnicalSetupPacket(
            schema_version="1.0.0",
            asset_pair="XAUUSD",
            strategy_name="PHX_M15",
            entry_price=2000.0,
            stop_loss=1995.0,
            take_profit=2015.0,
            timeframe="15m"
        )

        context_packet = MarketContextPacket(
            schema_version="1.0.0",
            source="test",
            asset_pair="XAUUSD",
            price=2000.0,
            volume_24h=1000.0
        )

        # 2. FIRE TECHNICAL SETUP (Simulating Bridge/Technical output)
        bus.publish("technical_setup", {
            "setup": setup_packet.model_dump_json(),
            "context": context_packet.model_dump_json()
        })

        # 3. RUN RISK WORKER (It should consume the setup and produce approval)
        # We will loop RiskWorker manually instead of `run()`
        messages = bus.consume("technical_setup", "test_risk_group", "test_e2e_consumer", count=1)
        self.assertTrue(len(messages) > 0, "No messages found in technical_setup stream")

        stream_name, stream_messages = messages[0]
        msg_id, payload = stream_messages[0]
        
        # Risk worker processes it manually
        setup = TechnicalSetupPacket.model_validate_json(payload["setup"])
        context = MarketContextPacket.model_validate_json(payload["context"])
        
        # Mock DB session for risk engine
        mock_db = MagicMock()
        mock_db.query().filter().order_by().limit().all.return_value = []
        mock_db.query().filter().scalar.return_value = 0.0

        approval = risk_worker.engine.evaluate(setup, context, {"daily_loss": 0.0, "consecutive_losses": 0}, mock_db)
        
        self.assertTrue(approval.is_approved, "Risk Engine should approve the valid test setup")
        
        bus.publish("risk_approval", {"payload": approval.model_dump_json()})
        bus.client.xack(stream_name, "test_risk_group", msg_id)

        # 4. ORCHESTRATOR CONSUMES APPROVAL
        orch_messages = bus.consume("risk_approval", "test_orch_group", "test_orch_consumer", count=1)
        self.assertTrue(len(orch_messages) > 0, "Orchestrator did not receive risk approval")

        stream_name, orch_msgs = orch_messages[0]
        orch_msg_id, orch_payload = orch_msgs[0]
        
        received_approval = RiskApprovalPacket.model_validate_json(orch_payload["payload"])
        self.assertEqual(received_approval.request_id, approval.request_id)
        
        # Final explicit check
        print(f"E2E Transition Complete: {setup.strategy_name} -> {approval.status}")
        self.assertEqual(approval.status, "ALLOW")

if __name__ == "__main__":
    unittest.main()
