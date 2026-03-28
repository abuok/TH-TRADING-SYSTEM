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
from shared.logic.risk import RiskEngine

class InMemoryEventBus:
    def __init__(self):
        self.streams = {}

    def publish(self, stream_name, payload):
        if stream_name not in self.streams:
            self.streams[stream_name] = []
        msg_id = f"{len(self.streams[stream_name])}-0"
        self.streams[stream_name].append((msg_id, payload))
        return msg_id

    def consume(self, stream_name, group_name, consumer_name, count=1, block=0):
        if stream_name not in self.streams or not self.streams[stream_name]:
            return []
        
        # Take the first 'count' messages
        msgs = self.streams[stream_name][:count]
        # Remove them so they aren't consumed again
        self.streams[stream_name] = self.streams[stream_name][count:]
        
        if not msgs:
            return []
        return [[stream_name, msgs]]

class MockClient:
    def xack(self, stream, group, msg_id):
        pass

class TestE2EWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_full_pipeline_flow(self):
        """
        Simulate the full E2E workflow: Bridge -> Technical -> Risk -> Orchestrator
        """
        in_memory_bus = InMemoryEventBus()

        with patch("shared.messaging.event_bus.EventBus.publish", side_effect=in_memory_bus.publish), \
             patch("shared.messaging.event_bus.EventBus.consume", side_effect=in_memory_bus.consume):

            # 1. SETUP WORKERS (Mocks for external dependencies)
            tech_worker = TechnicalWorker(pairs=["XAUUSD"])
            tech_worker.event_bus.client = MockClient()
            
            risk_engine = RiskEngine({
                "max_daily_loss": 30.0,
                "max_total_loss": 100.0,
                "max_consecutive_losses": 2,
                "min_rr_threshold": 2.0,
                "lot_size_limit": 0.1,
                "account_balance": 1000.0,
            })
            
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
            in_memory_bus.publish("technical_setup", {
                "setup": setup_packet.model_dump_json(),
                "context": context_packet.model_dump_json()
            })

            # 3. RUN RISK WORKER LOGIC
            messages = in_memory_bus.consume("technical_setup", "test_risk_group", "test_e2e_consumer", count=1)
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

            approval = risk_engine.evaluate(setup, context, {"daily_loss": 0.0, "consecutive_losses": 0}, mock_db)
            
            self.assertTrue(approval.is_approved, "Risk Engine should approve the valid test setup")
            
            in_memory_bus.publish("risk_approval", {"payload": approval.model_dump_json()})

            # 4. ORCHESTRATOR CONSUMES APPROVAL
            orch_messages = in_memory_bus.consume("risk_approval", "test_orch_group", "test_orch_consumer", count=1)
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
