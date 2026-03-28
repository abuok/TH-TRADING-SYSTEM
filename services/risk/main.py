import asyncio
import json
import logging
import os

from fastapi import FastAPI, Request

import shared.database.session as db_session
from shared.instrumentation.tracing import init_tracing, instrument_app
from shared.logic.risk import RiskEngine
from shared.messaging.event_bus import EventBus
from shared.security.middleware import setup_exception_handlers
from shared.security.rate_limiting import LIMITS, limiter, setup_rate_limiting
from shared.types.packets import (
    MarketContextPacket,
    RiskApprovalPacket,
    TechnicalSetupPacket,
)

from shared.logic.lockout_engine import LockoutEngine
from shared.types.enums import LockoutState

logger = logging.getLogger("RiskService")

app = FastAPI(title="Risk Service")

# Initialize v1.3 Core Logic
init_tracing("risk")
setup_rate_limiting(app)
instrument_app(app)
setup_exception_handlers(app)

event_bus = EventBus()

# Global state for context
current_context: dict = {}

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

lockout_engine = LockoutEngine({
    "max_daily_loss_pct": 3.0,
    "max_consecutive_losses": 3,
    "account_balance": 1000.0
})


async def risk_worker():
    """Background task to consume setups and context."""
    consumer_id = f"risk_service_{os.getpid()}"

    # Setup consumer groups
    event_bus.subscribe("market_context", "risk_group", consumer_id)
    event_bus.subscribe("technical_setup", "risk_group", consumer_id)

    logger.info("Risk Service: Worker started. Listening for topics...")

    while True:
        try:
            # 1. Consume context updates
            context_msgs = event_bus.consume(
                "market_context", "risk_group", consumer_id, count=10
            )
            if context_msgs:
                for _, msgs in context_msgs:
                    for msg_id, payload in msgs:
                        data = json.loads(payload["payload"])
                        current_context.update(data)
                        event_bus.client.xack("market_context", "risk_group", msg_id)

            # 2. Consume setups
            setup_msgs = event_bus.consume(
                "technical_setup", "risk_group", consumer_id, count=5
            )
            if setup_msgs:
                for _, msgs in setup_msgs:
                    for msg_id, payload in msgs:
                        data = json.loads(payload["payload"])
                        setup = TechnicalSetupPacket(**data)

                        # A. Fetch dynamic account state
                        db = db_session.SessionLocal()
                        try:
                            account_state = risk_engine.calculate_account_state(db)
                            
                            # B. Lockout Check
                            lockout_state, lockout_msg = lockout_engine.evaluate(account_state, db=db)
                            
                            if lockout_state != LockoutState.TRADEABLE:
                                approval = RiskApprovalPacket(
                                    schema_version="1.0.0",
                                    request_id=f"risk_lock_{msg_id}",
                                    status="BLOCK",
                                    is_approved=False,
                                    risk_score=0.0,
                                    max_position_size=0.0,
                                    rr_ratio=0.0,
                                    approver="LockoutEngine",
                                    reasons=[lockout_msg],
                                )
                            elif not current_context:
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
                                context_packet = MarketContextPacket(**current_context)
                                approval = risk_engine.evaluate(
                                    setup, context_packet, account_state, db=db
                                )
                        finally:
                            db.close()

                        # Publish result
                        event_bus.publish("risk_approval", approval.model_dump(mode="json"))
                        event_bus.client.xack("technical_setup", "risk_group", msg_id)
                        logger.info(
                            f"Risk Service: Processed setup {setup.asset_pair}. Status: {approval.status}"
                        )

            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Risk Service: Worker error - {e}", exc_info=True)
            await asyncio.sleep(5.0)


@app.on_event("startup")
async def startup_event():
    # Start the worker in the background
    asyncio.create_task(risk_worker())


@app.get("/health")
@limiter.limit(LIMITS["health"])
async def health_check(request: Request):
    return {
        "status": "healthy",
        "service": "risk",
        "has_context": bool(current_context),
    }
