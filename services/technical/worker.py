"""
services/technical/worker.py
Background worker for the Technical Service.
Processes quote streams and drives PHX Detectors.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from shared.logic.candle_aggregator import CandleAggregator
from shared.logic.phx_detector import PHXDetector, PHXStage
from shared.messaging.event_bus import EventBus
from shared.types.packets import TechnicalSetupPacket

logger = logging.getLogger("TechnicalWorker")

class TechnicalWorker:
    def __init__(self, pairs: list[str] = ["XAUUSD", "GBPJPY"]):
        self.event_bus = EventBus()
        self.aggregator = CandleAggregator(timeframes=["1m", "5m", "15m", "1h"])
        self.detectors: Dict[str, PHXDetector] = {pair: PHXDetector(pair) for pair in pairs}
        self.last_quote_time: Optional[datetime] = None
        self.is_running = False
        self.redis_prefix = "technical:detector"

    def _load_persisted_states(self):
        """Loads detector states from Redis on startup."""
        for symbol in self.detectors:
            try:
                key = f"{self.redis_prefix}:{symbol}"
                data = self.event_bus.client.get(key)
                if data:
                    serialized = json.loads(data)
                    self.detectors[symbol] = PHXDetector.from_dict(serialized)
                    logger.info("Restored persisted state for %s: %s", symbol, self.detectors[symbol].stage.name)
            except Exception as e:
                logger.error("Failed to restore state for %s: %s", symbol, e)

    def _save_state(self, symbol: str):
        """Persists a detector's state to Redis."""
        try:
            key = f"{self.redis_prefix}:{symbol}"
            serialized = self.detectors[symbol].to_dict()
            self.event_bus.client.set(key, json.dumps(serialized))
        except Exception as e:
            logger.error("Failed to persist state for %s: %s", symbol, e)

    async def run(self):
        """Main loop: consume quotes and update detectors."""
        self._load_persisted_states()
        self.is_running = True
        logger.info("Technical Worker started. Monitoring: %s", list(self.detectors.keys()))
        
        # Subscribe to quote stream
        self.event_bus.subscribe("quote", "technical_group", "worker_1")

        while self.is_running:
            try:
                # Read from Redis Stream
                messages = self.event_bus.consume("quote", "technical_group", "worker_1", count=10)
                
                if not messages:
                    await asyncio.sleep(0.1)
                    continue

                for stream, msg_list in messages:
                    for msg_id, payload in msg_list:
                        data = json.loads(payload["payload"])
                        symbol = data["symbol"]
                        bid = data["bid"]
                        ask = data["ask"]
                        ts_str = data.get("timestamp")
                        ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
                        self.last_quote_time = datetime.now(timezone.utc) # Receive time
                        self._check_staleness()

                        if symbol in self.detectors:
                            completed_candles = self.aggregator.update(symbol, bid, ask, ts)
                            for candle in completed_candles:
                                prev_stage = self.detectors[symbol].stage
                                self.detectors[symbol].update(candle)
                                
                                # If stage advanced, publish a setup packet and persist
                                if self.detectors[symbol].stage != prev_stage:
                                    self._publish_setup(symbol, prev_stage)
                                    self._save_state(symbol)

                        # Acknowledge message
                        self.event_bus.client.xack("quote", "technical_group", msg_id)

            except Exception as e:
                logger.error("Error in Technical Worker loop: %s", e, exc_info=True)
                await asyncio.sleep(1.0)

    def _publish_setup(self, symbol: str, prev_stage: Optional[PHXStage] = None):
        detector = self.detectors[symbol]
        prev_name = prev_stage.name if prev_stage else "UNKNOWN"
        logger.info("PHX Setup Transition [%s]: %s -> %s", symbol, prev_name, detector.stage.name)
        
        # Build packet
        packet = TechnicalSetupPacket(
            schema_version="1.0.2",
            asset_pair=symbol,
            strategy_name="PHX_V1",
            entry_price=detector.sweep_high_low or 0.0,  # Placeholder entry
            stop_loss=detector.sweep_level or 0.0,       # Use sweep level as SL
            take_profit=0.0,                            # Needs logic for TP
            timeframe="15m",                            # Primary timeframe
            session_levels={}                           # Should be populated
        )
        
        # Add custom metadata to the packet payload if needed (schema debt)
        data = packet.model_dump(mode="json")
        data["stage"] = detector.stage.name
        data["reason_codes"] = detector.reason_codes
        data["score"] = detector.get_score()

        self.event_bus.publish("technical_setup", data)

    def _check_staleness(self):
        """Check if market data is too old and invalidate detectors."""
        if not self.last_quote_time:
            return
            
        now = datetime.now(timezone.utc)
        if self.last_quote_time and (now - self.last_quote_time).total_seconds() > 300:
            logger.warning("Market data STALE (>300s). Invalidating all detectors.")
            for detector in self.detectors.values():
                if not detector.is_invalidated:
                    detector.invalidate()
                    detector.reason_codes.append("STALE_DATA_OUTAGE")

    def stop(self):
        self.is_running = False
