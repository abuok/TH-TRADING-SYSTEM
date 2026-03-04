"""
V1 prototype safety tests — preserved for reference only.
The modules tested here (risk_engine, core_models) have been archived to
scripts/v1_demo/ and are no longer on the import path.
"""

import unittest
import pytest
from unittest.mock import patch

# Skip the entire module if V1 modules are not importable (expected in production)
risk_engine = pytest.importorskip(
    "risk_engine",
    reason="V1 risk_engine archived to scripts/v1_demo/ — skipping V1 safety tests",
)
core_models = pytest.importorskip(
    "core_models",
    reason="V1 core_models archived to scripts/v1_demo/ — skipping V1 safety tests",
)

RiskEngine = risk_engine.RiskEngine
SignalPacket = core_models.SignalPacket
ScorePacket = core_models.ScorePacket
Direction = core_models.Direction
RiskDecision = core_models.RiskDecision


class TestTradingDeskSafety(unittest.TestCase):
    def test_session_boundaries(self):
        from datetime import time

        # London Session: 10:00 - 19:00 EAT
        # NY Session: 15:00 - 23:59 EAT
        self.assertFalse(time(10, 0) <= time(9, 0) <= time(19, 0))
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
