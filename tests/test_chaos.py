import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import redis
from sqlalchemy.exc import OperationalError

# Ensure project root is in sys.path for importing shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.messaging.event_bus import EventBus
from shared.logic.risk import RiskEngine
from services.technical.worker import TechnicalWorker
from shared.types.packets import TechnicalSetupPacket, Candle
from shared.logic.accounts import calculate_account_state

class TestChaos(unittest.TestCase):

    @patch("redis.from_url")
    def test_eventbus_blackout_behavior(self, mock_redis):
        """Verify EventBus handles Redis outages by failing gracefully and returning None."""
        mock_client = MagicMock()
        # Simulate connection failure
        mock_client.xadd.side_effect = redis.exceptions.ConnectionError("Connection refused")
        mock_redis.return_value = mock_client
        
        bus = EventBus()
        # Data to publish
        data = {"test": "data"}
        
        # Should attempt retries (3 by default)
        # Note: EventBus.publish internal retries will sleep, let's patch time.sleep to speed up
        with patch("time.sleep", return_value=None):
            result = bus.publish("test_stream", data)
        
        self.assertIsNone(result, "Publish should return None on failure")
        self.assertEqual(mock_client.xadd.call_count, 3, "Should retry 3 times before giving up")

    @patch("shared.database.session.SessionLocal")
    def test_risk_engine_db_partition(self, mock_session_factory):
        """Verify RiskEngine components handle DB outages safely."""
        mock_session = MagicMock()
        mock_session.query.side_effect = OperationalError("Local", "Statement", "DB Down")
        mock_session_factory.return_value = mock_session
        
        engine = RiskEngine({"max_daily_loss": 30.0})
        
        # Verify shared calculation raises error (to be caught by service worker)
        with self.assertRaises(OperationalError):
            calculate_account_state(mock_session)
            
        # Verify RiskEngine calculation raises error
        with self.assertRaises(OperationalError):
            engine.calculate_account_state(mock_session)

    @patch("shared.messaging.event_bus.EventBus")
    def test_technical_service_stale_quote_invalidation(self, mock_bus_class):
        """Verify TechnicalWorker invalidates detectors when market data stops flowing."""
        from shared.logic.phx_detector import PHXStage
        
        worker = TechnicalWorker()
        # 1. Setup a detector in a non-IDLE state
        detector = worker.detectors["XAUUSD"]
        detector.stage = PHXStage.BIAS
        detector.is_invalidated = False
        
        # 2. Simulate last quote being 6 minutes ago (360s > 300s limit)
        worker.last_quote_time = datetime.now(timezone.utc) - timedelta(seconds=360)
        
        # 3. Trigger staleness check
        worker._check_staleness()
        
        self.assertTrue(detector.is_invalidated, "Detector should be invalidated due to stale data")
        self.assertEqual(detector.stage, PHXStage.IDLE, "Detector should reset to IDLE")
        self.assertIn("STALE_DATA_OUTAGE", detector.reason_codes)

if __name__ == "__main__":
    unittest.main()
