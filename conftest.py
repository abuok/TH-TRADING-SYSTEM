import os
import pytest
from sqlalchemy.orm import sessionmaker
import shared.database.session as session
from shared.database.models import Base

@pytest.fixture(scope="session", autouse=True)
def force_test_db():
    # Force in-memory SQLite for the entire session
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

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
