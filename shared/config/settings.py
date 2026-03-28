"""
shared/config/settings.py
-------------------------
Centralized configuration manager for the TH Trading System.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class SystemSettings(BaseSettings):
    # --- Service Ports ---
    DASHBOARD_PORT: int = 8000
    INGESTION_PORT: int = 8001
    TECHNICAL_PORT: int = 8002
    RISK_PORT: int = 8003
    ORCHESTRATOR_PORT: int = 8004
    JOURNAL_PORT: int = 8005

    # --- Trading ---
    ASSET_PAIRS: list[str] = ["XAUUSD", "GBPJPY"]

    # --- Database & Redis ---
    DATABASE_URL: str = "sqlite:///./trading.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Security ---
    DASHBOARD_AUTH_ENABLED: bool = True
    DASHBOARD_USER: str = "admin"
    DASHBOARD_PASSWORD: str = "admin"

    # --- Operational Guards ---
    STALENESS_THRESHOLD_SECONDS: int = 300  # 5 minutes
    RATE_LIMIT_SECONDS: int = 10            # 1 request per 10s per endpoint

    # --- RISK LOGIC ---
    MAX_DAILY_LOSS_PCT: float = 2.0
    MAX_CONSECUTIVE_LOSSES: int = 3
    DEFAULT_ACCOUNT_BALANCE: float = 100000.0

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Singleton instance
settings = SystemSettings()
