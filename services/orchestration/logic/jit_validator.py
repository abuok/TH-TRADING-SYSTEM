"""
services/orchestration/logic/jit_validator.py
Implements synchronous Just-In-Time validation for ticket confirmation.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Tuple, Dict, Any

from sqlalchemy.orm import Session
from shared.database.models import OrderTicket, Packet
from shared.types.enums import LockoutState, SessionState
from shared.logic.lockout_engine import LockoutEngine
from shared.logic.alignment import AlignmentEngine
from shared.logic.sessions import SessionEngine, get_nairobi_time

class JITValidator:
    def __init__(self, lockout_config: Dict[str, Any]):
        self.lockout_engine = LockoutEngine(lockout_config)
        self.alignment_engine = AlignmentEngine()

    def validate(self, db: Session, ticket: OrderTicket) -> Tuple[bool, str, str]:
        """
        Runs the 5-step JIT validation sequence.
        Returns (is_valid, reason_code, validation_hash).
        """
        now_utc = datetime.now(timezone.utc)
        now_nairobi = get_nairobi_time()

        # Step 1: Lockout Check
        account_state = {
            "daily_loss": 0.0,  # Placeholder
            "account_balance": 10000.0,  # Placeholder
            "consecutive_losses": 0 # Placeholder
        }
        lockout_state, lockout_msg = self.lockout_engine.evaluate(account_state, db=db)
        if lockout_state == LockoutState.HARD_LOCK:
            return False, f"REJECTED_JIT: HARD_LOCK - {lockout_msg}", ""

        # Step 2: Staleness / Expiry Check
        if ticket.expires_at and now_utc > ticket.expires_at.replace(tzinfo=timezone.utc):
            return False, "EXPIRED: Ticket TTL exceeded", ""

        # Step 3: Session Check
        session_label = SessionEngine.get_session_state(now_nairobi, ticket.pair)
        if session_label == SessionState.OUT_OF_SESSION:
            return False, "REJECTED_JIT: Market Out of Session", ""

        # Step 4: Alignment Check (Bias, Events, Direction)
        pair_fund_db = db.query(Packet).filter(
            Packet.packet_type == "PairFundamentalsPacket",
            Packet.data["asset_pair"].as_string() == ticket.pair
        ).order_by(Packet.created_at.desc()).first()

        ctx_db = db.query(Packet).filter(
            Packet.packet_type == "MarketContextPacket"
        ).order_by(Packet.created_at.desc()).first()

        if not pair_fund_db or not ctx_db:
            return False, "REJECTED_JIT: Missing market data for alignment", ""

        # Bias State Check
        if pair_fund_db.data.get("is_invalidated"):
             return False, "REJECTED_JIT: Bias Invalidated since ticket generation", ""

        setup_data = {
            "asset_pair": ticket.pair,
            "entry_price": ticket.entry_price,
            "take_profit": ticket.take_profit_1
        }
        
        alignment_decision = self.alignment_engine.evaluate(
            setup_data, 
            pair_fund_db.data, 
            ctx_db.data, 
            db=db,
            now_nairobi=now_nairobi
        )
        
        if not alignment_decision.is_aligned:
            return False, f"REJECTED_JIT: {'; '.join(alignment_decision.reason_codes)}", ""

        # Step 5: State Hash Calculation (Audit Proof)
        state_vector = {
            "ticket_id": ticket.ticket_id,
            "lockout": lockout_state.value,
            "session": session_label,
            "bias_id": pair_fund_db.id,
            "ctx_id": ctx_db.id,
            "confirm_ts": now_utc.isoformat()
        }
        state_hash = hashlib.sha256(json.dumps(state_vector, sort_keys=True).encode()).hexdigest()

        return True, "ALIGNED", state_hash
