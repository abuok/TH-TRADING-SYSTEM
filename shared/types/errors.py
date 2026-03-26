"""
shared/types/errors.py
----------------------
Structured exception hierarchy for TH-TRADING-SYSTEM.

All trading system exceptions carry:
  - ``error_code``  : machine-readable identifier for alerting / dashboards
  - ``context``     : dict of runtime values that caused the error
  - ``severity``    : "INFO" | "WARNING" | "ERROR" | "CRITICAL"

Usage::

    raise MarketDataError(
        message="Market data stale",
        context={"age_seconds": 420, "max_age_seconds": 300},
    )
"""

from __future__ import annotations

from typing import Any


class TradingSystemError(Exception):
    """Base exception for all TH-TRADING-SYSTEM errors."""

    error_code: str = "TRADING_SYSTEM_ERROR"
    default_severity: str = "ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        severity: str | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code or self.__class__.error_code
        self.context: dict[str, Any] = context or {}
        self.severity = severity or self.__class__.default_severity
        super().__init__(self.message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"severity={self.severity!r})"
        )


# ── Market / data errors ──────────────────────────────────────────────────────

class MarketDataError(TradingSystemError):
    """Raised when market data is absent, stale, or malformed."""

    error_code = "MARKET_DATA_INVALID"
    default_severity = "WARNING"


class ContextStaleError(MarketDataError):
    """Raised when market context exceeds the maximum allowed age."""

    error_code = "CONTEXT_STALE"
    default_severity = "WARNING"


# ── Risk / evaluation errors ──────────────────────────────────────────────────

class RiskEvaluationError(TradingSystemError):
    """Raised when the risk engine cannot complete its evaluation."""

    error_code = "RISK_EVAL_FAILED"
    default_severity = "WARNING"


class RRRatioError(RiskEvaluationError):
    """Raised when a setup's R:R ratio is below the minimum threshold."""

    error_code = "RR_RATIO_BELOW_MIN"
    default_severity = "WARNING"


class DailyLossLimitError(RiskEvaluationError):
    """Raised when the daily loss limit has been breached."""

    error_code = "DAILY_LOSS_LIMIT_BREACHED"
    default_severity = "CRITICAL"


# ── Execution errors ──────────────────────────────────────────────────────────

class ExecutionError(TradingSystemError):
    """Raised when an order cannot be placed or managed on the broker."""

    error_code = "EXECUTION_FAILED"
    default_severity = "CRITICAL"


class BrokerConnectionError(ExecutionError):
    """Raised when the MT5 bridge is unreachable."""

    error_code = "BROKER_CONNECTION_FAILED"
    default_severity = "CRITICAL"


class OrderRejectedError(ExecutionError):
    """Raised when the broker rejects an order."""

    error_code = "ORDER_REJECTED"
    default_severity = "ERROR"


# ── Database errors ───────────────────────────────────────────────────────────

class DatabaseError(TradingSystemError):
    """Raised when a database operation fails unexpectedly."""

    error_code = "DB_ERROR"
    default_severity = "CRITICAL"


class RecordNotFoundError(DatabaseError):
    """Raised when an expected database record does not exist."""

    error_code = "RECORD_NOT_FOUND"
    default_severity = "WARNING"


# ── Service / integration errors ──────────────────────────────────────────────

class ServiceUnavailableError(TradingSystemError):
    """Raised when a downstream service does not respond."""

    error_code = "SERVICE_UNAVAILABLE"
    default_severity = "CRITICAL"


class ConfigurationError(TradingSystemError):
    """Raised when a required configuration value is missing or invalid."""

    error_code = "CONFIGURATION_ERROR"
    default_severity = "CRITICAL"


# ── Validation errors ─────────────────────────────────────────────────────────

class ValidationError(TradingSystemError):
    """Raised when input data fails business-rule validation."""

    error_code = "VALIDATION_ERROR"
    default_severity = "WARNING"
