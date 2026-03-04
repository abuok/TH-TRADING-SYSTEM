import uuid
from core_models import SignalPacket, Direction
from session_manager import SessionManager
import random


class SignalGenerator:
    """
    Generates signals for specific symbols.
    In V1, these can be random or rule-based for demonstration.
    """

    SYMBOLS = ["XAUUSD", "GBPJPY"]

    @classmethod
    def generate_signal(cls, symbol: str) -> SignalPacket:
        if not SessionManager.is_in_session():
            raise ValueError(
                f"Cannot generate signal for {symbol} outside of active sessions."
            )

        # Heuristic simulation for V1
        direction = random.choice([Direction.LONG, Direction.SHORT])
        entry = 2030.50 if symbol == "XAUUSD" else 190.20
        # Add some random variance
        entry += random.uniform(-1, 1)

        sl_offset = 5.0 if symbol == "XAUUSD" else 0.50
        tp_offset = 15.0 if symbol == "XAUUSD" else 1.50

        sl = entry - sl_offset if direction == Direction.LONG else entry + sl_offset
        tp = entry + tp_offset if direction == Direction.LONG else entry - tp_offset

        return SignalPacket(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            direction=direction,
            entry=round(entry, 2),
            sl=round(sl, 2),
            tp=round(tp, 2),
            timestamp=SessionManager.get_current_time_eat().isoformat(),
            strategy="V1_Breakout",
        )
