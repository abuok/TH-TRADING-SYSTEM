import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from sqlalchemy.pool import StaticPool


def get_engine(url=None):
    url = url or os.getenv(
        "DATABASE_URL", "postgresql://admin:admin@localhost:5432/trading_db"
    )
    if url == "sqlite:///:memory:":
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url)


# Default instances
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Only useful for simple dev without Alembic
    Base.metadata.create_all(bind=engine)
