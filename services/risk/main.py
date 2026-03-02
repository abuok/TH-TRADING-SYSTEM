import json
import os

from fastapi import FastAPI
from shared.logic.risk import RiskEngine
from shared.messaging.event_bus import EventBus
import asyncio

import logging
from typing import Dict

from shared.types.packets import (
    MarketContextPacket,
    RiskApprovalPacket,
    TechnicalSetupPacket,
)

logger = logging.getLogger("RiskService")

app = FastAPI(title="Risk Service")
event_bus = EventBus()

# Global state for context and account
current_context: Dict = {}
account_state = {"daily_loss": 0.0, "total_loss": 0.0, "consecutive_losses": 0}

risk_engine = RiskEngine(
    {
        "max_daily_loss": 30.0,
        "max_total_loss": 100.0,
        "max_consecutive_losses": 2,
        "min_rr_threshold": 2.0,
        "lot_size_limit": 0.1,
        "account_balance": 1000.0,
    }
)


async def risk_worker():
    """Background task to consume setups and context."""
    consumer_id = f"risk_service_{os.getpid()}"

    # Setup consumer groups
    event_bus.subscribe("market_context", "risk_group", consumer_id)
    event_bus.subscribe("technical_setups", "risk_group", consumer_id)

    logger.info("Risk Service: Worker started. Listening for topics...")

    while True:
        try:
            # Consume context updates
            context_msgs = event_bus.consume(
                "market_context", "risk_group", consumer_id, count=10
            )
            for _, msgs in context_msgs:
                for msg_id, payload in msgs:
                    data = json.loads(payload["payload"])
                    current_context.update(data)
                    logger.debug(f"Risk Service: Updated market context from {msg_id}")

            # Consume setups
            setup_msgs = event_bus.consume(
                "technical_setups", "risk_group", consumer_id, count=5
            )
            for _, msgs in setup_msgs:
                for msg_id, payload in msgs:
                    data = json.loads(payload["payload"])
                    setup = TechnicalSetupPacket(**data)

                    # Wrap current_context in model for engine
                    context_packet = (
                        MarketContextPacket(**current_context)
                        if current_context
                        else None
                    )

                    if not context_packet:
                        logger.warning(
                            "Risk Service: No market context available. Blocking setup."
                        )
                        # Emit a failed approval (fail closed)
                        approval = RiskApprovalPacket(
                            schema_version="1.0.0",
                            request_id=f"risk_fail_{msg_id}",
                            status="BLOCK",
                            is_approved=False,
                            risk_score=0.0,
                            max_position_size=0.0,
                            rr_ratio=0.0,
                            approver="RiskServiceV1",
                            reasons=["No market context available"],
                        )
                    else:
                        approval = risk_engine.evaluate(
                            setup, context_packet, account_state
                        )

                    # Publish result
                    event_bus.publish("risk_approvals", approval.dict())
                    logger.info(
                        f"Risk Service: Processed setup {setup.asset_pair}. Status: {approval.status}"
                    )

            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Risk Service: Worker error - {e}")
            await asyncio.sleep(5.0)


@app.on_event("startup")
async def startup_event():
    # Start the worker in the background
    asyncio.create_task(risk_worker())


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "risk",
        "has_context": bool(current_context),
    }
