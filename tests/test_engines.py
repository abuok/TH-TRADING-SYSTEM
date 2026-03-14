from datetime import datetime, timedelta, timezone

import pytest
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database.session import Base
from shared.logic.alignment import AlignmentEngine
from shared.logic.lockout_engine import LockoutEngine
from shared.types.enums import LockoutState


@pytest.fixture(scope="module")
def sqlite_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return TestingSessionLocal()


def test_lockout_trigger_blocks_execution():
    engine = LockoutEngine(
        config={"max_daily_loss_pct": 2.0, "max_consecutive_losses": 3}
    )

    # Passing state
    state, msg = engine.evaluate(
        {"daily_loss": 0.0, "account_balance": 10000.0, "consecutive_losses": 0},
        db=None,
    )
    assert state == LockoutState.HARD_LOCK  # DB=None triggers a fail-close!

    # Real passing state without DB checks (mocked behavior for testing pure limits if we bypass DB fail-close, but since it fails closed, let's just make a mock DB)
    class MockDB:
        def query(self, *args, **kwargs):
            class MockQuery:
                def filter(self, *args, **kwargs):
                    return self

                def first(self):
                    return None

            return MockQuery()

    # Under limit
    state, msg = engine.evaluate(
        {"daily_loss": 50.0, "account_balance": 10000.0, "consecutive_losses": 0},
        db=MockDB(),
    )
    assert state == LockoutState.TRADEABLE

    # Over daily loss limit (200 >= 2% of 10000)
    state, msg = engine.evaluate(
        {"daily_loss": 200.0, "account_balance": 10000.0, "consecutive_losses": 0},
        db=MockDB(),
    )
    assert state == LockoutState.HARD_LOCK
    assert "Daily loss 2.0% >=" in msg


def test_alignment_fails_on_stale_bias():
    now_nairobi = datetime.now(pytz.timezone("Africa/Nairobi"))

    # Stale by 3 hours
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()

    setup_data = {
        "asset_pair": "GBPJPY",
        "entry_price": 1.0,
        "take_profit": 1.5,  # BUY
    }

    # Passing state: Direction match, but age is bad.
    pair_fundamentals = {
        "bias_score": 5.0,  # Buy
        "is_invalidated": False,
        "created_at": stale_time,
    }

    context_data = {"high_impact_events": []}

    # This should return UNALIGNED because of Bias Age > 120mins
    engine = AlignmentEngine()
    decision = engine.evaluate(
        setup_data, pair_fundamentals, context_data, now_nairobi=now_nairobi
    )

    assert decision.is_aligned is False
    assert any("FAILED: BiasState" in reason for reason in decision.reason_codes)
