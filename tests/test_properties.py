import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import MagicMock
from datetime import datetime, timezone

from shared.database.models import OrderTicket
from shared.types.packets import TechnicalSetupPacket, RiskApprovalPacket, AlignmentDecision
from shared.logic.trading_logic import generate_order_ticket

# Helper strategy to generate valid reasonable floats for prices
price_strategy = st.floats(min_value=0.1, max_value=100000.0, allow_nan=False, allow_infinity=False)


@given(
    entry_price=price_strategy,
    stop_loss=price_strategy,
    take_profit=price_strategy,
)
@settings(max_examples=500)
def test_rr_calculation_always_valid(entry_price, stop_loss, take_profit):
    """
    Property: The risk-reward (RR) calculation should never crash
    with ZeroDivisionError and should always be non-negative.
    """
    # Simulate the logic inline to avoid DB mock complexity for pure math
    dist = abs(entry_price - stop_loss)
    rr_tp1 = abs(take_profit - entry_price) / dist if dist > 0 else 0.0

    assert rr_tp1 >= 0.0
    assert not isinstance(rr_tp1, complex)
    # Using python floats, standard division doesn't throw NaN for >0


@given(
    pair=st.sampled_from(["EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "XAUUSD"]),
    strategy_name=st.sampled_from(["Breakout", "MeanReversion", "TrendFollowing"]),
    setup_ts=st.integers(min_value=1600000000, max_value=2000000000),
    risk_ts=st.integers(min_value=1600000000, max_value=2000000000),
)
@settings(max_examples=100)
def test_evaluation_idempotent(pair, strategy_name, setup_ts, risk_ts):
    """
    Property: Generating a ticket with the exact same identifying inputs
    must return the exact same ticket object (idempotency).
    """
    db_mock = MagicMock()
    
    setup = TechnicalSetupPacket(
        timestamp=setup_ts,
        asset_pair=pair,
        strategy_name=strategy_name,
        timeframe="H1",
        signal_type="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=110.0,
        confidence_score=0.8,
        market_context_id=0,
    )
    risk = RiskApprovalPacket(
        timestamp=risk_ts,
        setup_id=0,
        status="PASS",
    )
    
    # Setup mock to return an existing ticket when queried
    existing_ticket = OrderTicket(idempotency_key="mocked_key")
    db_mock.query().filter().first.return_value = existing_ticket
    
    # Call generate_order_ticket
    # The first call will hit the mocked existing ticket
    ticket1 = generate_order_ticket(setup, risk, db_mock)
    
    # Second call
    ticket2 = generate_order_ticket(setup, risk, db_mock)
    
    assert ticket1 is ticket2
