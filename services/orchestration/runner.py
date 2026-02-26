import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

from shared.logic.sessions import TradingSessions
from shared.logic.phx_detector import PHXDetector
from shared.logic.risk import RiskEngine
from shared.types.packets import (
    MarketContextPacket, 
    TechnicalSetupPacket, 
    RiskApprovalPacket, 
    DecisionPacket
)
import shared.database.session as db_session
from shared.database.models import Packet as DBPacket, Run as DBRun
from shared.logic.notifications import NotificationService, ConsoleNotificationAdapter
from shared.logic.governance import GovernanceEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Orchestrator")

class Orchestrator:
    def __init__(self, risk_config: dict, dry_run: bool = False, notifier: Optional[NotificationService] = None):
        self.risk_engine = RiskEngine(risk_config)
        self.sessions = TradingSessions()
        self.dry_run = dry_run
        self.is_active = False
        self.run_id = None
        self.detectors: Dict[str, PHXDetector] = {}
        self.notifier = notifier or NotificationService([ConsoleNotificationAdapter()])
        
        self.db = db_session.SessionLocal()
        self.governance = GovernanceEngine(self.db)
        
        # Idempotency / De-dup tracking
        self.last_alerts = {} # (asset_pair, alert_type) -> last_score
        self.ttl_map = {
            "MarketContextPacket": 30,
            "TechnicalSetupPacket": 120,
            "RiskApprovalPacket": 60
        }

    def get_detector(self, asset_pair: str) -> PHXDetector:
        if asset_pair not in self.detectors:
            self.detectors[asset_pair] = PHXDetector(asset_pair)
        return self.detectors[asset_pair]

    def start_run(self):
        """Create a new run entry in the database."""
        try:
            db = db_session.SessionLocal()
            run_uid = f"run_{datetime.now().timestamp()}"
            new_run = DBRun(run_id=run_uid, status="running")
            db.add(new_run)
            db.commit()
            db.refresh(new_run)
            self.run_id = new_run.id
            db.close()
            logger.info(f"Started new run with ID: {self.run_id} ({run_uid})")
            self.notifier.notify(f"Trading Session Started: {run_uid}", level="INFO")
        except Exception as e:
            logger.error(f"Failed to start run: {e}")
            self.run_id = 0 # Fallback

    async def pre_session_briefing(self, asset_pair: str, historical_candles: list):
        """Analyze market bias and session levels before trading starts."""
        if not self.run_id: self.start_run()
        logger.info(f"Starting pre-session briefing for {asset_pair}...")
        
        # Use the correct method name from TradingSessions
        levels = self.sessions.compute_all_levels(historical_candles)
        logger.info(f"Session Levels: {levels}")
        return levels

    async def live_loop(self, asset_pair: str, interval_seconds: int = 60):
        """Main loop during active trading sessions."""
        if not self.run_id: self.start_run()
        self.is_active = True
        logger.info(f"Starting live loop for {asset_pair} (Dry Run: {self.dry_run})")
        
        while self.is_active:
            # 1. Check Global/Service Kill Switch
            if self.governance.is_halted("HALT_ALL") or self.governance.is_halted("HALT_SERVICE", "Orchestrator"):
                logger.warning("Orchestrator HALTED by kill switch.")
                if self.dry_run: break
                await asyncio.sleep(interval_seconds)
                continue

            # 2. Check Pair Kill Switch
            if self.governance.is_halted("HALT_PAIR", asset_pair):
                logger.warning(f"Pair {asset_pair} HALTED by kill switch.")
                if self.dry_run: break
                await asyncio.sleep(interval_seconds)
                continue

            context = self.get_latest_market_context(asset_pair)
            
            # 3. Staleness Guard
            if not self.governance.validate_packet_freshness("MarketContextPacket", context.timestamp, self.ttl_map):
                logger.error(f"Abandoning loop iteration for {asset_pair} due to stale context.")
                if self.dry_run: break
                await asyncio.sleep(interval_seconds)
                continue

            # 4. Check for "forming" status with Dedup
            detector = self.get_detector(asset_pair)
            score = detector.get_score()
            if 50 <= score < 100:
                last_score = self.last_alerts.get((asset_pair, "FORMING"))
                if last_score is None or abs(score - last_score) >= 10: # Only notify if significantly changed
                    self.notifier.notify(f"Setup Forming on {asset_pair}: Score {score}", level="INFO")
                    self.last_alerts[(asset_pair, "FORMING")] = score

            setup = self.scan_for_setup(asset_pair, context)
            
            if setup:
                # 5. Technical Setup Staleness Guard
                if not self.governance.validate_packet_freshness("TechnicalSetupPacket", setup.timestamp, self.ttl_map):
                    if self.dry_run: break
                    await asyncio.sleep(interval_seconds)
                    continue

                self.notifier.notify(f"Setup Execute-Ready on {asset_pair}", level="SUCCESS")
                
                account_state = {"daily_loss": 0.0, "total_loss": 0.0, "consecutive_losses": 0}
                approval = self.risk_engine.evaluate(setup, context, account_state)
                
                if not approval.is_approved:
                    self.notifier.notify(f"Risk BLOCK on {asset_pair}: {', '.join(approval.reasons)}", level="ERROR")
                
                decision = self.generate_decision(setup, approval, self.dry_run)
                
                # Persist
                self.persist_packet("DecisionPacket", decision)
                
                # Output for Human Review
                self.output_decision(decision)
            
            if self.dry_run:
                break
                
            await asyncio.sleep(interval_seconds)

    def output_decision(self, decision: DecisionPacket):
        """High-visibility output for human review."""
        color = "\033[92m" if "EXECUTE" in decision.action else "\033[91m"
        reset = "\033[0m"
        logger.info(f"\n{color}--- DECISION PACKET ---{reset}")
        logger.info(f"Asset: {decision.asset_pair} | Strategy: {decision.strategy_name}")
        logger.info(f"Action: {decision.action} | RR: {decision.rr_ratio}")
        logger.info(f"Risk Status: {decision.risk_status}")
        if decision.risk_reasons:
            logger.info(f"Reasons: {', '.join(decision.risk_reasons)}")
        logger.info(f"{color}-----------------------{reset}\n")

    def persist_packet(self, packet_type: str, packet: any):
        """Store packet in database for forensic auditing."""
        if self.run_id == 0 or self.run_id is None: 
            logger.warning("No active run_id, skipping persistence.")
            return
        try:
            db = db_session.SessionLocal()
            # Ensure data is JSON serializable (handling datetime, etc.)
            if hasattr(packet, 'model_dump'):
                data = packet.model_dump(mode='json')
            elif hasattr(packet, 'dict'):
                # Fallback for Pydantic V1 or similar
                import json
                data = json.loads(packet.json())
            else:
                data = packet

            db_packet = DBPacket(
                run_id=self.run_id,
                packet_type=packet_type,
                schema_version=packet.schema_version,
                data=data
            )
            db.add(db_packet)
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Failed to persist packet: {e}")

    def scan_for_setup(self, asset_pair: str, context: MarketContextPacket) -> Optional[TechnicalSetupPacket]:
        # For demo, we return a mock setup if price hits a certain level
        if context.price > 0: # Always "detect" something for demo
            return TechnicalSetupPacket(
                schema_version="1.0.0",
                asset_pair=asset_pair,
                strategy_name="PHX",
                entry_price=context.price,
                stop_loss=context.price * 0.99,
                take_profit=context.price * 1.03,
                timeframe="1H",
                timestamp=datetime.now(timezone.utc)
            )
        return None

    def get_latest_market_context(self, asset_pair: str) -> MarketContextPacket:
        # Mocking incoming data
        return MarketContextPacket(
            schema_version="1.0.0",
            source="OrchestratorMock",
            asset_pair=asset_pair,
            price=65000.0,
            volume_24h=1000.0,
            timestamp=datetime.now(timezone.utc)
        )

    def generate_decision(self, setup: TechnicalSetupPacket, approval: RiskApprovalPacket, dry_run: bool) -> DecisionPacket:
        action = "EXECUTE" if approval.is_approved else "BLOCK"
        if dry_run:
            action = f"DRY_RUN_{action}"
            
        return DecisionPacket(
            schema_version="1.0.0",
            asset_pair=setup.asset_pair,
            strategy_name=setup.strategy_name,
            score=75.0, # Placeholder
            bias_score=0.5, # Placeholder
            rr_ratio=approval.rr_ratio,
            risk_status=approval.status,
            risk_reasons=approval.reasons,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            action=action,
            is_dry_run=dry_run,
            timestamp=datetime.now(timezone.utc)
        )

async def main():
    risk_config = {
        "max_daily_loss": 30.0,
        "max_total_loss": 100.0,
        "max_consecutive_losses": 2,
        "min_rr_threshold": 2.0,
        "lot_size_limit": 0.1,
        "account_balance": 1000.0
    }
    
    orchestrator = Orchestrator(risk_config, dry_run=True)
    
    # Pre-session (Briefing)
    await orchestrator.pre_session_briefing("BTCUSD", [])
    
    # Live Loop
    await orchestrator.live_loop("BTCUSD")
    
    logger.info("End of Session. Finalizing Reports...")

if __name__ == "__main__":
    db_session.init_db()
    asyncio.run(main())
