import os
import yaml
import logging
from datetime import datetime, timedelta, timezone, time as time_
from typing import Dict, Any, List, Optional

import pytz
from sqlalchemy.orm import Session
from sqlalchemy import func

from shared.types.enums import SessionState
from shared.types.packets import AlignmentDecision
from shared.logic.sessions import SessionEngine, get_nairobi_time

NAIROBI = pytz.timezone("Africa/Nairobi")
logger = logging.getLogger("AlignmentEngine")

class AlignmentEngine:
    """
    Evaluates binary Alignment metrics (ALIGNED vs UNALIGNED).
    No fractional multipliers or confidences are allowed.
    Incorporate key safety rules formerly in Guardrails.
    """

    def __init__(self, config_path: str = os.path.join("config", "alignment_config.yaml")):
        self.cfg = self._load_config(config_path)
        logger.info("AlignmentEngine initialized with binary constitutional rules.")

    def _load_config(self, path: str) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load alignment config: {e}")
        
        # Defaults
        cfg.setdefault("news_window", [-15.0, 45.0])
        cfg.setdefault("bias_expiry_minutes", 120)
        cfg.setdefault("quote_staleness_limit_seconds", 15.0)
        cfg.setdefault("eod_gap_minutes", [-5, 10]) # 23:55 to 00:10
        return cfg

    @staticmethod
    def _check_bias_direction(setup_direction: str, bias_score: float) -> bool:
        if setup_direction == "BUY" and bias_score > 0:
            return True
        if setup_direction == "SELL" and bias_score < 0:
            return True
        return False

    def _check_bias_state(self, pair_fundamentals: Dict[str, Any]) -> bool:
        if pair_fundamentals.get("is_invalidated", False):
            return False
            
        created_at_str = pair_fundamentals.get("created_at")
        if not created_at_str:
            return False
            
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            now_utc = datetime.now(timezone.utc)
            expiry = self.cfg.get("bias_expiry_minutes", 120)
            if (now_utc - created_at).total_seconds() / 60.0 > expiry:
                return False
        except (ValueError, TypeError):
            return False
        return True

    def _check_event_proximity(self, context_data: Dict[str, Any], now_nairobi: datetime) -> bool:
        events = context_data.get("high_impact_events", [])
        window = self.cfg.get("news_window", [-15.0, 45.0])
        
        for ev in events:
            time_str = ev.get("time")
            if not time_str: continue
            try:
                candidates = [now_nairobi.date()]
                if int(time_str.split(":")[0]) < 6:
                    candidates.append(now_nairobi.date() + timedelta(days=1))
                
                for d in candidates:
                    ev_dt = NAIROBI.localize(datetime.strptime(f"{d.isoformat()} {time_str}", "%Y-%m-%d %H:%M"))
                    diff = (ev_dt - now_nairobi).total_seconds() / 60.0
                    if window[0] <= diff <= window[1]:
                        return False
            except ValueError: continue
        return True

    def _check_eod_gap(self, now_nairobi: datetime) -> bool:
        # Broker EOD is typically 00:00 EET/EEST.
        # Convering Nairobi (UTC+3) to EET (UTC+2/3) simplified check:
        # We'll just use a fixed Nairobi window if EET conversion is too complex here
        # EOD Gap [-5, 10] around midnight.
        t = now_nairobi.time()
        # Block 23:55 - 00:10
        if t >= time_(23, 55) or t <= time_(0, 10):
            return False
        return True

    def _check_quote_staleness(self, asset_pair: str, db: Session, now_utc: datetime) -> bool:
        from shared.database.models import QuoteStaleLog
        limit = self.cfg.get("quote_staleness_limit_seconds", 15.0)
        cutoff = now_utc - timedelta(minutes=2)
        
        # Max staleness in last 2 mins
        max_stale = db.query(func.max(QuoteStaleLog.stale_duration_seconds)).filter(
            QuoteStaleLog.symbol == asset_pair,
            QuoteStaleLog.created_at >= cutoff
        ).scalar()
        
        if max_stale is None: return False # Fail closed if no telemetry
        return float(max_stale) <= limit

    def evaluate(
        self,
        setup_data: Dict[str, Any],
        pair_fundamentals: Dict[str, Any],
        context_data: Dict[str, Any],
        db: Optional[Session] = None,
        now_nairobi: Optional[datetime] = None
    ) -> AlignmentDecision:
        now_nairobi = now_nairobi or get_nairobi_time()
        asset_pair = setup_data.get("asset_pair", "UNKNOWN")
        
        tp = float(setup_data.get("take_profit", 0))
        ep = float(setup_data.get("entry_price", 1))
        setup_dir = "BUY" if tp > ep else "SELL"
        bias_score = float(pair_fundamentals.get("bias_score", 0))
        
        results = {
            "Direction": self._check_bias_direction(setup_dir, bias_score),
            "BiasState": self._check_bias_state(pair_fundamentals),
            "Events": self._check_event_proximity(context_data, now_nairobi),
            "Session": SessionState(SessionEngine.get_session_state(now_nairobi, asset_pair)) != SessionState.OUT_OF_SESSION,
            "EOD_Gap": self._check_eod_gap(now_nairobi)
        }
        
        if db:
            now_utc = now_nairobi.astimezone(timezone.utc)
            results["Staleness"] = self._check_quote_staleness(asset_pair, db, now_utc)
        
        is_aligned = all(results.values())
        reasons = [f"FAILED: {k}" for k, v in results.items() if not v]
        if is_aligned: reasons = ["All binary alignment checks passed."]
        
        return AlignmentDecision(
            asset_pair=asset_pair,
            is_aligned=is_aligned,
            reason_codes=reasons
        )
