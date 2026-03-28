"""
shared/logic/policy_router.py
Regime-Adaptive Policy Router for selecting guardrails profiles based on market conditions.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import Any

import yaml
from pydantic import BaseModel

from shared.logic.sessions import get_session_label

logger = logging.getLogger("PolicyRouter")


class PolicyDecision(BaseModel):
    policy_name: str
    policy_hash: str
    policy_config: dict[str, Any]
    reasons: list[str]
    regime_signals: dict[str, Any]


class PolicyRouter:
    def __init__(self, policies_dir: str = "config/policies"):
        self.policies_dir = policies_dir
        self.policies: dict[str, dict[str, Any]] = {}
        self.policy_hashes: dict[str, str] = {}
        self._load_policies()

    def _load_policies(self):
        """Loads all YAML policies from the policies directory."""
        if not os.path.exists(self.policies_dir):
            logger.warning(f"Policies directory {self.policies_dir} not found.")
            return

        for filename in os.listdir(self.policies_dir):
            if filename.endswith(".yaml"):
                path = os.path.join(self.policies_dir, filename)
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    config = yaml.safe_load(content)
                    if config and "policy_name" in config:
                        name = config["policy_name"]
                        self.policies[name] = config
                        self.policy_hashes[name] = hashlib.sha256(
                            content.encode()
                        ).hexdigest()[:8]

        logger.info(
            f"Loaded {len(self.policies)} policy profiles: {list(self.policies.keys())}"
        )

    def select_policy(
        self,
        movers_data: Any,
        context_data: Any,
        pair_fundamentals: Any,
        now_nairobi: datetime,
    ) -> PolicyDecision:
        """
        Deterministic logic to select the best policy profile.
        Priority: RISK_OFF > EVENT_HEAVY > BEST_CONDITIONS > DEFAULT
        """
        reasons = []
        signals = {}

        # 1. Extract Signals (Handle Dict or Pydantic Model)
        def _get(obj, key, default=None):
            if hasattr(obj, "dict"):  # Pydantic v1
                return getattr(obj, key, default)
            if hasattr(obj, "model_dump"):  # Pydantic v2
                return getattr(obj, key, default)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        sentiment_flags = _get(movers_data, "sentiment_flags", [])
        events = _get(context_data, "high_impact_events", [])
        session = get_session_label(now_nairobi)
        bias_score = _get(pair_fundamentals, "bias_score", 0.0)

        signals["sentiment_flags"] = sentiment_flags
        signals["event_count"] = len(events)
        signals["session"] = session
        signals["bias_score"] = bias_score

        # 2. Dynamic Selection Logic from YAML
        rules_path = os.path.join(self.policies_dir, "selection_rules.yaml")
        if os.path.exists(rules_path):
            with open(rules_path, encoding="utf-8") as f:
                rules_config = yaml.safe_load(f)
                for rule in rules_config.get("rules", []):
                    if self._evaluate_rule(rule, signals):
                        # Format reasons with data
                        formatted_reasons = [
                            r.format(**signals) for r in rule.get("reasons", [])
                        ]
                        return self._build_decision(rule["name"], formatted_reasons, signals)

        # Fallback to hardcoded logic if YAML fails or missing
        reasons.append("FALLBACK: selection_rules.yaml missing or no rules matched.")
        return self._build_decision("Default", reasons, signals)

    def _evaluate_rule(self, rule: dict, signals: dict) -> bool:
        """Evaluates a single rule's conditions against market signals."""
        conditions = rule.get("conditions", [])
        if not conditions:
            return True # Default rule matches nothing

        for cond in conditions:
            field = cond["field"]
            val = signals.get(field)
            target = cond["value"]
            op = cond["operator"]

            if op == "contains":
                if target not in (val or []): return False
            elif op == "gte":
                if not (val >= target): return False
            elif op == "in":
                if val not in target: return False
            elif op == "abs_gte":
                if not (abs(val or 0.0) >= target): return False
            # Add more operators as needed
            
        return True

    def _build_decision(
        self, name: str, reasons: list[str], signals: dict[str, Any]
    ) -> PolicyDecision:
        if name not in self.policies:
            logger.error(
                f"Selected policy '{name}' not found in loaded policies. Falling back to Default."
            )
            name = "Default"
            reasons.append("FALLBACK: Selected policy was missing from config.")

        if name not in self.policies:
            # Default is also missing — fail hard so operators know the system is misconfigured
            raise RuntimeError(
                "PolicyRouter: Neither the selected policy nor 'Default' was found in "
                f"{self.policies_dir}. Cannot proceed — guardrails would be unconfigured. "
                "Ensure config/policies/policy_default.yaml exists."
            )

        config = self.policies.get(name, {})
        return PolicyDecision(
            policy_name=name,
            policy_hash=self.policy_hashes.get(name, "unknown"),
            policy_config=config,
            reasons=reasons,
            regime_signals=signals,
        )
