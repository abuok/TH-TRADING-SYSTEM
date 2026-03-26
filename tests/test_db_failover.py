import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from shared.database.session import get_db, TransactionDecorator


def test_get_db_rollback_on_error():
    """
    Ensures the FastAPI get_db dependency generator correctly rolls
    back the session if an endpoint throws a SQLAlchemyError.
    """
    # Create the generator
    db_gen = get_db()
    
    # We need to mock SessionLocal so get_db yields our mock
    with patch("shared.database.session.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        db_gen = get_db()
        db = next(db_gen)  # Yields the session
        
        # Simulate endpoint throwing an error back into the generator
        with pytest.raises(OperationalError):
            db_gen.throw(OperationalError("Mock DB disconnect", params={}, orig=Exception()))
            
        # Verify rollback and close were called on the mock DB
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


def test_transaction_decorator_rollback_on_error():
    """
    Ensures functions wrapped in @TransactionDecorator.transactional
    properly rollback the session when exceptions occur mid-transaction.
    """
    with patch("shared.database.session.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        @TransactionDecorator.transactional
        def failing_business_logic(db):
            raise OperationalError("Deadlock detected", params={}, orig=Exception())
            
        # Executing the wrapped function should raise and rollback
        with pytest.raises(OperationalError):
            failing_business_logic()
            
        # Verify rollback and close
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.close.assert_called_once()


def test_engine_pool_resilience_configuration():
    """
    Verifies that the production engine configuration includes
    pool_pre_ping=True for automatic reconnection on transient errors.
    """
    from shared.database.session import get_engine
    
    engine = get_engine("postgresql://postgres:postgres@localhost:5432/trading_test")
    
    # pool_pre_ping emits a 'SELECT 1' before checkout to verify connection liveness.
    # This natively handles transient drops (reconnecting automatically).
    assert engine.pool._pre_ping is True
    assert engine.pool.size() == 20
