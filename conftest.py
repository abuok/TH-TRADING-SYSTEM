import os
import pytest
from sqlalchemy.orm import sessionmaker
from shared.database.session import get_engine, Base
import shared.database.session as session

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    # Force in-memory SQLite for ALL tests
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    
    # Re-initialize the engine and SessionLocal to use the memory DB
    test_engine = get_engine("sqlite:///:memory:")
    session.engine = test_engine
    session.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Create all tables (including new ones like kill_switches)
    Base.metadata.create_all(bind=test_engine)
    
    yield
    
    # Optional: cleanup
    Base.metadata.drop_all(bind=test_engine)
