import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Base
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


def get_engine(url=None):
    url = url or os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/trading_journal"
    )
    if url == "sqlite:///:memory:":
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


# Default instances
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
