import os

# FORCE SQLite for all tests immediately before any imports trigger engine initialization
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Force mock providers so tests never hit real DB/broker for quotes/specs
os.environ.setdefault("SPEC_PROVIDER", "mock")
os.environ.setdefault("PRICE_PROVIDER", "mock")

import pytest
from sqlalchemy.orm import sessionmaker
import shared.database.session as session
from shared.database.models import Base

@pytest.fixture(scope="session", autouse=True)
def force_test_db():
    pass

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    # Re-initialize the engine and SessionLocal for each test to ensure isolation
    # with SQLite memory + StaticPool
    test_engine = session.get_engine("sqlite:///:memory:")
    session.engine = test_engine
    session.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Create all tables (including new ones like kill_switches)
    Base.metadata.create_all(bind=test_engine)
    
    yield test_engine
    
    # Cleanup
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    # Reset any global provider overrides set during the test
    from shared.providers.price_quote import set_price_quote_provider
    set_price_quote_provider(None)
