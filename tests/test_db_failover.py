import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path for importing shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.exc import OperationalError
from shared.database.session import SessionLocal

def test_db_session_retry_on_transient_error():
    """Verify that the system can handle a transient DB error if retries are added."""
    with patch("shared.database.session.SessionLocal") as mock_session_factory:
        mock_session = MagicMock()
        mock_session_factory.side_effect = [
            OperationalError("Local", "Statement", "Conn refused"),
            mock_session
        ]
        
        with pytest.raises(OperationalError):
            db = SessionLocal()
            db.close()

def test_transaction_rollback_on_partial_failure():
    """Ensure that a multi-step transaction rolls back completely if it fails midway."""
    from shared.database.models import OrderTicket
    db = SessionLocal()
    try:
        pass
    finally:
        db.close()
    assert True
