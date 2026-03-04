from core_models import SignalPacket, ScorePacket, RiskPacket, RiskDecision
from session_manager import SessionManager


class RiskEngine:
    """
    Non-executing Risk Engine (V1).
    Deterministic rules ONLY.
    """

    MAX_DAILY_SIGNALS = 5
    MIN_CONFIDENCE = 60.0

    # Track signal counts (In-memory for V1 Sim)
    _signal_count_today = 0

    @classmethod
    def evaluate_risk(cls, signal: SignalPacket, score: ScorePacket) -> RiskPacket:
        decision = RiskDecision.APPROVE
        reason = "All checks passed."

        # Rule 1: Session Check
        session_check = SessionManager.is_in_session()
        if not session_check:
            decision = RiskDecision.BLOCK
            reason = "Signal outside of active trading sessions (EAT)."

        # Rule 2: Max Signals Check
        if cls._signal_count_today >= cls.MAX_DAILY_SIGNALS:
            decision = RiskDecision.BLOCK
            reason = f"Daily Max Signal Limit reached ({cls.MAX_DAILY_SIGNALS})."

        # Rule 3: Minimum Confidence Check
        if score.confidence_score < cls.MIN_CONFIDENCE:
            decision = RiskDecision.BLOCK
            reason = f"Confidence {score.confidence_score}% below threshold {cls.MIN_CONFIDENCE}%."

        # Increment count if approved (V1 heuristic)
        if decision == RiskDecision.APPROVE:
            cls._signal_count_today += 1

        return RiskPacket(
            signal_id=signal.id,
            decision=decision,
            reason=reason,
            max_drawdown_check=True,  # Mocked for V1
            session_check=session_check,
        )
