"""
shared/logic/alignment.py
Enforces the strictly binary Alignment Gate evaluated exclusively at TRIGGER.
"""

from datetime import datetime, timedelta
from typing import Dict, Any

import pytz

from shared.types.enums import SessionState
from shared.types.packets import AlignmentDecision
from shared.logic.sessions import SessionEngine

NAIROBI = pytz.timezone("Africa/Nairobi")

class AlignmentEngine:
    """
    Evaluates binary Alignment metrics (ALIGNED vs UNALIGNED).
    No fractional multipliers or confidences are allowed.
    """

    @staticmethod
    def _check_bias_direction(setup_direction: str, bias_score: float) -> bool:
        # Bias Score: Positive is Bullish, Negative is Bearish.
        if setup_direction == "BUY" and bias_score > 0:
            return True
        if setup_direction == "SELL" and bias_score < 0:
            return True
        return False

    @staticmethod
    def _check_bias_state(pair_fundamentals: Dict[str, Any]) -> bool:
        # Must not be INVALIDATED or EXPIRED.
        is_invalidated = pair_fundamentals.get("is_invalidated", False)
        if is_invalidated:
            return False
            
        # Age check
        created_at_str = pair_fundamentals.get("created_at")
        if not created_at_str:
            return False
            
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            now_utc = datetime.now(pytz.utc)
            # 120 minutes is the EXPIRED cutoff
            age_minutes = (now_utc - created_at).total_seconds() / 60.0
            if age_minutes > 120:
                return False
        except (ValueError, TypeError):
            return False
            
        return True

    @staticmethod
    def _check_event_proximity(context_data: Dict[str, Any], now_nairobi: datetime) -> bool:
        events = context_data.get("high_impact_events", [])
        if not events:
            return True

        for ev in events:
            ev_time_str = ev.get("time", "")
            if not ev_time_str:
                continue
                
            try:
                # Same approach as guardrails: check today and tomorrow
                candidates = [now_nairobi.date()]
                ev_hour = int(ev_time_str.split(":")[0])
                if ev_hour < 6:
                    candidates.append(now_nairobi.date() + timedelta(days=1))
                
                for candidate_date in candidates:
                    ev_dt = datetime.strptime(
                        f"{candidate_date.isoformat()} {ev_time_str}", "%Y-%m-%d %H:%M"
                    )
                    ev_nairobi = NAIROBI.localize(ev_dt)
                    
                    diff_minutes = (ev_nairobi - now_nairobi).total_seconds() / 60.0
                    
                    # Fails if the event is WITHIN [-15, +45] minutes of now
                    if -15.0 <= diff_minutes <= 45.0:
                        return False
            except ValueError:
                continue
        return True

    @staticmethod
    def _check_session_window(now_nairobi: datetime, asset_pair: str) -> bool:
        # Primary or Secondary Execution Windows are allowed.
        state = SessionEngine.get_session_state(now_nairobi, asset_pair)
        allowed_states = [
            SessionState.LONDON_OPEN.value,
            SessionState.LONDON_MID.value,
            SessionState.NY_OPEN.value
        ]
        return state in allowed_states

    @classmethod
    def evaluate(
        cls,
        setup_data: Dict[str, Any],
        pair_fundamentals: Dict[str, Any],
        context_data: Dict[str, Any],
        now_nairobi: datetime
    ) -> AlignmentDecision:
        asset_pair = setup_data.get("asset_pair", "UNKNOWN")
        
        # 1. Bias Direction Match
        tp = float(setup_data.get("take_profit", 0))
        ep = float(setup_data.get("entry_price", 1))
        setup_direction = "BUY" if tp > ep else "SELL"
        bias_score = float(pair_fundamentals.get("bias_score", 0))
        
        dir_ok = cls._check_bias_direction(setup_direction, bias_score)
        
        # 2. Bias State Match (Not ExPIRED/INVALIDATED)
        state_ok = cls._check_bias_state(pair_fundamentals)
        
        # 3. Event Proximity
        events_ok = cls._check_event_proximity(context_data, now_nairobi)
        
        # 4. Session State Match
        session_ok = cls._check_session_window(now_nairobi, asset_pair)
        
        reasons = []
        is_aligned = True
        
        if not dir_ok:
            is_aligned = False
            reasons.append(f"Direction mismatch: Setup {setup_direction} vs Bias {bias_score}")
        if not state_ok:
            is_aligned = False
            reasons.append("Bias state EXPIRED or INVALIDATED")
        if not events_ok:
            is_aligned = False
            reasons.append("Failed Event Proximity: Red folder event inside [-15, +45] minute window")
        if not session_ok:
            is_aligned = False
            state_label = SessionEngine.get_session_state(now_nairobi, asset_pair)
            reasons.append(f"Session {state_label} is not a valid Execution Window")
            
        if is_aligned:
            reasons.append("All alignment binary checks passed.")

        return AlignmentDecision(
            asset_pair=asset_pair,
            is_aligned=is_aligned,
            reason_codes=reasons
        )
