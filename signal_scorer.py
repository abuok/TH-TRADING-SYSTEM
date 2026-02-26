from core_models import SignalPacket, ScorePacket
import random

class SignalScorer:
    """
    Evaluates signal quality based on simple deterministic metrics.
    V1: Heuristic based on hypothetical market state.
    """
    @classmethod
    def score_signal(cls, signal: SignalPacket) -> ScorePacket:
        # V1: Mock scoring based on symbol/strategy
        base_score = 70.0
        if signal.symbol == "XAUUSD":
            # Gold is more volatile, higher uncertainty penalty
            score = base_score + random.uniform(-10, 5)
        else:
            score = base_score + random.uniform(-5, 10)

        # In V1, we add a mock ATR check
        atr = 15.20 if signal.symbol == "XAUUSD" else 0.45
        
        return ScorePacket(
            signal_id=signal.id,
            confidence_score=round(max(0, min(100, score)), 2),
            metadata={"atr": atr, "volume_delta": "UP", "session_volatility": "HIGH"}
        )
