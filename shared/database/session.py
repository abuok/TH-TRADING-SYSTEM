import logging
import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from .models import Base

logger = logging.getLogger(__name__)

# ── Pool configuration ───────────────────────────────────────────────────────
_POOL_SIZE = 20        # Base connections kept alive
_MAX_OVERFLOW = 10     # Additional burst connections
_POOL_RECYCLE = 3600   # Recycle connections after 1 hour (avoids stale TCP)
_POOL_TIMEOUT = 30     # Max seconds to wait for a free connection


def get_engine(url: str | None = None):
    url = url or os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/trading_journal"
    )
    if url.startswith("sqlite:///:memory:"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if url.startswith("sqlite://"):
        # File-based SQLite: use StaticPool (single thread) or NullPool
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            pool_recycle=_POOL_RECYCLE,
        )
    # PostgreSQL / production: full QueuePool tuning
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        pool_recycle=_POOL_RECYCLE,
        pool_pre_ping=True,
        pool_timeout=_POOL_TIMEOUT,
        # expire_on_commit=False set on SessionLocal below for perf
    )


# Default instances
engine = get_engine()


# ── Pool diagnostics ─────────────────────────────────────────────────────────
@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record) -> None:  # type: ignore[type-arg]
    pool = engine.pool
    logger.debug(
        "DB connection opened — pool checked-out: %s / size: %s",
        pool.checkedout(),
        pool.size(),
    )


@event.listens_for(engine, "close")
def _on_close(dbapi_conn, connection_record) -> None:  # type: ignore[type-arg]
    logger.debug("DB connection returned to pool")


def dispose_engine() -> None:
    """Gracefully close all pooled connections. Call on service shutdown."""
    engine.dispose()
    logger.info("Database connection pool disposed")


def get_db_pool_health() -> dict:
    """Return live pool stats for health endpoints and Prometheus gauges."""
    pool = engine.pool
    checked_out: int = pool.checkedout()
    size: int = pool.size()
    return {
        "active_connections": checked_out,
        "idle_connections": max(0, size - checked_out),
        "total_pool_size": size,
        "max_pool_size": size + pool._max_overflow,  # type: ignore[attr-defined]
        "overflow_used": max(0, checked_out - size),
    }


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Don't re-fetch objects after commit (faster reads)
)


def get_db():
    """Get database session with automatic transaction management.

    Yields:
        SQLAlchemy Session with proper rollback on exceptions

    Raises:
        SQLAlchemyError: If database operation fails

    Example:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error occurred: {e}", exc_info=True)
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in database session: {e}", exc_info=True)
        raise
    finally:
        db.close()


class TransactionDecorator:
    """Decorator for automatic transaction management in functions."""

    @staticmethod
    def transactional(func):
        """Decorator to wrap functions with transaction handling.

        Usage:
            @TransactionDecorator.transactional
            def update_order(db: Session, order_id: int, status: str):
                order = db.query(OrderTicket).get(order_id)
                order.status = status
                # Auto-commits on success, rolls back on exception
        """
        from functools import wraps

        @wraps(func)
        def wrapper(db: Session = None, *args, **kwargs):
            if db is None:
                db = SessionLocal()
                session_created = True
            else:
                session_created = False

            try:
                result = func(db, *args, **kwargs)
                if session_created:
                    db.commit()
                return result
            except SQLAlchemyError as e:
                if session_created:
                    db.rollback()
                logger.error(
                    f"Transaction failed in {func.__name__}: {e}", exc_info=True
                )
                raise
            except Exception as e:
                if session_created:
                    db.rollback()
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                raise
            finally:
                if session_created:
                    db.close()

        return wrapper


def init_db():
    # Only useful for simple dev without Alembic
    Base.metadata.create_all(bind=engine)
