from shared.database.session import init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DBInit")

if __name__ == "__main__":
    logger.info("Initializing database schema...")
    init_db()
    logger.info("Database schema initialized successfully.")
