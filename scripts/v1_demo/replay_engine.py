import json
import time
from core_models import SignalPacket
from signal_scorer import SignalScorer
from risk_engine import RiskEngine
from journal_service import JournalingService


class ReplayEngine:
    """
    Simulation / Replay Mode (V1).
    Reads historical signals and replays them through the Scorer and Risk Engine.
    """

    @classmethod
    def run_replay(cls, history_file: str, delay: float = 0.5):
        print(f"=== Replay Mode: {history_file} ===")

        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
            return

        for entry in history:
            # Reconstruct SignalPacket
            signal = SignalPacket(**entry)

            print(
                f"Replaying: {signal.timestamp} | {signal.symbol} | {signal.direction}"
            )

            # Process through the same deterministic pipe
            score = SignalScorer.score_signal(signal)
            risk = RiskEngine.evaluate_risk(signal, score)

            # Log to forensic journal
            JournalingService.log_entry(signal, score, risk)

            time.sleep(delay)

        print("-" * 50)
        print("Replay complete.")
