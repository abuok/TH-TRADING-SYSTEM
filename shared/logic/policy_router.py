"""
shared/logic/policy_router.py
Regime-Adaptive Policy Router for selecting guardrails profiles based on market conditions.
"""
import os
import yaml
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel

from shared.logic.sessions import get_session_label

logger = logging.getLogger("PolicyRouter")

class PolicyDecision(BaseModel):
    policy_name: str
    policy_hash: str
    policy_config: Dict[str, Any]
    reasons: List[str]
    regime_signals: Dict[str, Any]

class PolicyRouter:
    def __init__(self, policies_dir: str = "config/policies"):
        self.policies_dir = policies_dir
        self.policies: Dict[str, Dict[str, Any]] = {}
        self.policy_hashes: Dict[str, str] = {}
        self._load_policies()

    def _load_policies(self):
        """Loads all YAML policies from the policies directory."""
        if not os.path.exists(self.policies_dir):
            logger.warning(f"Policies directory {self.policies_dir} not found.")
            return

        for filename in os.listdir(self.policies_dir):
            if filename.endswith(".yaml"):
                path = os.path.join(self.policies_dir, filename)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    config = yaml.safe_load(content)
                    if config and "policy_name" in config:
                        name = config["policy_name"]
                        self.policies[name] = config
                        self.policy_hashes[name] = hashlib.sha256(content.encode()).hexdigest()[:8]
        
        logger.info(f"Loaded {len(self.policies)} policy profiles: {list(self.policies.keys())}")

    def select_policy(
        self,
        movers_data: Dict[str, Any],
        context_data: Dict[str, Any],
        pair_fundamentals: Dict[str, Any],
        now_nairobi: datetime
    ) -> PolicyDecision:
        """
        Deterministic logic to select the best policy profile.
        Priority: RISK_OFF > EVENT_HEAVY > BEST_CONDITIONS > DEFAULT
        """
        reasons = []
        signals = {}
        
        # 1. Extract Signals
        sentiment_flags = movers_data.get("sentiment_flags", [])
        events = context_data.get("high_impact_events", [])
        session = get_session_label(now_nairobi)
        bias_score = pair_fundamentals.get("bias_score", 0.0)
        confidence = pair_fundamentals.get("confidence_label", "LOW")

        signals["sentiment_flags"] = sentiment_flags
        signals["event_count"] = len(events)
        signals["session"] = session
        signals["bias_score"] = bias_score
        signals["confidence"] = confidence

        # 2. Selection Logic
        
        # A. RISK OFF (Highest Priority)
        # Check for RISK_OFF flag or very poor sentiment
        if "RISK_OFF" in sentiment_flags:
            reasons.append("Market sentiment flagged as RISK_OFF.")
            return self._build_decision("Risk Off", reasons, signals)

        # B. EVENT HEAVY
        # Check for upcoming high-impact events (e.g., > 2 events in current context)
        if len(events) >= 3:
            reasons.append(f"High event density detected ({len(events)} red-folder events).")
            return self._build_decision("Event Heavy", reasons, signals)

        # C. BEST CONDITIONS
        # Strong bias, high confidence, and in core sessions
        if (session in ["LONDON", "NEW YORK"] and 
            abs(bias_score) >= 4.0 and 
            confidence == "HIGH"):
            reasons.append(f"Strong confluence: {session} session + High confidence bias ({bias_score}).")
            return self._build_decision("Best Conditions", reasons, signals)

        # D. DEFAULT
        reasons.append("No specialized market regime detected. Using baseline policy.")
        return self._build_decision("Default", reasons, signals)

    def _build_decision(self, name: str, reasons: List[str], signals: Dict[str, Any]) -> PolicyDecision:
        if name not in self.policies:
            logger.error(f"Selected policy {name} not found in loaded policies. Falling back to Default.")
            name = "Default"
            reasons.append("FALLBACK: Selected policy was missing from config.")

        config = self.policies.get(name, {})
        return PolicyDecision(
            policy_name=name,
            policy_hash=self.policy_hashes.get(name, "unknown"),
            policy_config=config,
            reasons=reasons,
            regime_signals=signals
        )
