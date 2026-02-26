import json
import os
from datetime import datetime
from core_models import ForensicJournalEntry, SignalPacket, ScorePacket, RiskPacket

class JournalingService:
    """
    Forensic Journaling Service (V1).
    Logs every decision path to a file.
    """
    JOURNAL_FILE = "trading_journal.json"

    @classmethod
    def log_entry(cls, signal: SignalPacket, score: ScorePacket, risk: RiskPacket):
        # Determine status
        final_status = "REJECTED" if risk.decision == "BLOCK" else "ACCEPTED (SIMULATED)"
        
        entry = ForensicJournalEntry(
            timestamp=datetime.now().isoformat(),
            signal=signal,
            score=score,
            risk=risk,
            final_status=final_status
        )

        entries = []
        if os.path.exists(cls.JOURNAL_FILE):
            with open(cls.JOURNAL_FILE, "r") as f:
                try:
                    entries = json.load(f)
                except json.JSONDecodeError:
                    entries = []

        entries.append(entry.dict())

        with open(cls.JOURNAL_FILE, "w") as f:
            json.dump(entries, f, indent=4)
        
        # Log to console for CLI demo
        print(f"[{entry.timestamp}] {signal.symbol} {signal.direction} -> {score.confidence_score}% -> {final_status} ({risk.reason})")
