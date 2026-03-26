import json
import logging
import sys
from datetime import datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings for structured logging.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra attributes
        extra_data = getattr(record, "extra_data", {})
        if extra_data:
            log_record.update(extra_data)

        if record.exc_info:
            from typing import cast, TYPE_CHECKING
            if TYPE_CHECKING:
                from types import TracebackType
                exc_info_type = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
            else:
                exc_info_type = Any
            
            log_record["exception"] = self.formatException(cast(exc_info_type, record.exc_info))

        return json.dumps(log_record)


def setup_production_logging(level: int = logging.INFO) -> None:
    """
    Configs logging to use JSON formatting for production environments.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # Sanitize: Remove root handlers if they exist to avoid duplicate logs
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(handler)
    root.setLevel(level)

    # Silence verbose third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
