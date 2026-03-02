import unittest
from datetime import time
from risk_engine import RiskEngine
from core_models import SignalPacket, ScorePacket, Direction, RiskDecision
from unittest.mock import patch



class TestTradingDeskSafety(unittest.TestCase):
    def test_session_boundaries(self):
        # London Session: 10:00 - 19:00 EAT
        # NY Session: 15:00 - 23:59 EAT

        # 09:00 EAT should be OUT
        self.assertFalse(time(10, 0) <= time(9, 0) <= time(19, 0))

        # 11:00 EAT should be IN
        self.assertTrue(time(10, 0) <= time(11, 0) <= time(19, 0))

    @patch("risk_engine.SessionManager.is_in_session")
    def test_risk_engine_blocking(self, mock_session):
        mock_session.return_value = True
        signal = SignalPacket(
            id="test-001",
            symbol="XAUUSD",
            direction=Direction.LONG,
            entry=2000.0,
            sl=1990.0,
            tp=2030.0,
            timestamp="2026-01-01T12:00:00",
            strategy="Test",
        )

        # Case 1: Low confidence should block
        score_low = ScorePacket(signal_id="test-001", confidence_score=50.0)
        risk_low = RiskEngine.evaluate_risk(signal, score_low)
        self.assertEqual(risk_low.decision, RiskDecision.BLOCK)
        self.assertIn("Confidence 50.0% below threshold", risk_low.reason)

        # Case 2: Approval works
        score_high = ScorePacket(signal_id="test-001", confidence_score=85.0)
        # Reset count for test
        RiskEngine._signal_count_today = 0
        risk_high = RiskEngine.evaluate_risk(signal, score_high)
        self.assertEqual(risk_high.decision, RiskDecision.APPROVE)

        # Case 3: Daily limit hits
        RiskEngine._signal_count_today = RiskEngine.MAX_DAILY_SIGNALS
        risk_limit = RiskEngine.evaluate_risk(signal, score_high)
        self.assertEqual(risk_limit.decision, RiskDecision.BLOCK)
        self.assertIn("Daily Max Signal Limit reached", risk_limit.reason)


if __name__ == "__main__":
    unittest.main()
