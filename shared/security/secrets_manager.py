"""
Secrets management for production deployments.

Supports loading secrets from:
1. Environment variables (highest priority)
2. AWS Secrets Manager
3. HashiCorp Vault
4. Local .env file (development only)
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


class SecretsManager:
    """Centralized secrets management with multiple backend support."""

    # Required secrets for production
    REQUIRED_SECRETS = {
        "DATABASE": ["POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_HOST"],
        "API": ["API_SECRET_KEY", "JWT_ALGORITHM"],
        "BRIDGE": ["MT5_API_KEY", "MT5_MASTER_PASSWORD"],
        "NOTIFICATIONS": ["TELEGRAM_BOT_TOKEN"],
    }

    def __init__(self, environment: str = "development"):
        """Initialize secrets manager.

        Args:
            environment: deployment environment (development/staging/production)
        """
        self.environment = environment
        self._secrets: dict[str, Any] = {}
        self._load_secrets()

    def _load_secrets(self) -> None:
        """Load secrets from highest-priority source available."""
        # Priority 1: AWS Secrets Manager (production)
        if self.environment == "production" and self._try_aws_secrets():
            return

        # Priority 2: HashiCorp Vault (staging/production)
        if self.environment in ("staging", "production") and self._try_vault():
            return

        # Priority 3: Environment variables (all environments)
        self._load_from_env()

        # Priority 4: Local .env file (development only)
        if self.environment == "development":
            self._load_from_dotenv()

    def _try_aws_secrets(self) -> bool:
        """Try loading secrets from AWS Secrets Manager."""
        try:
            import boto3

            client = boto3.client(
                "secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1")
            )
            response = client.get_secret_value(
                SecretId=os.getenv("AWS_SECRET_NAME", "trading-system/prod")
            )

            if "SecretString" in response:
                self._secrets = json.loads(response["SecretString"])
                return True
        except Exception as e:
            print(f"AWS Secrets Manager not available: {e}")
        return False

    def _try_vault(self) -> bool:
        """Try loading secrets from HashiCorp Vault."""
        try:
            import hvac

            vault_addr = os.getenv("VAULT_ADDR", "https://vault.example.com:8200")
            vault_token = os.getenv("VAULT_TOKEN")

            if not vault_token:
                return False

            client = hvac.Client(url=vault_addr, token=vault_token)
            response = client.secrets.kv.v2.read_secret_version(
                path=f"trading-system/{self.environment}"
            )
            self._secrets = response["data"]["data"]
            return True
        except Exception as e:
            print(f"HashiCorp Vault not available: {e}")
        return False

    def _load_from_env(self) -> None:
        """Load secrets from environment variables."""
        for _category, secret_names in self.REQUIRED_SECRETS.items():
            for secret_name in secret_names:
                value = os.getenv(secret_name)
                if value:
                    self._secrets[secret_name] = value

    def _load_from_dotenv(self) -> None:
        """Load secrets from .env file (development only)."""
        dotenv_path = Path(".env")
        if dotenv_path.exists():
            with open(dotenv_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        self._secrets[key.strip()] = value.strip().strip("\"'")

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a secret value."""
        return self._secrets.get(key, default)

    def require(self, key: str) -> str:
        """Get a required secret, raise error if missing."""
        if key not in self._secrets:
            raise ValueError(f"Required secret '{key}' not found")
        return str(self._secrets[key])

    def validate_production_secrets(self) -> bool:
        """Validate all required secrets are present for production."""
        if self.environment != "production":
            return True

        missing = []
        for _category, secret_names in self.REQUIRED_SECRETS.items():
            for secret_name in secret_names:
                if secret_name not in self._secrets:
                    missing.append(f"{category}/{secret_name}")

        if missing:
            raise ValueError(f"Missing production secrets: {', '.join(missing)}")
        return True

    def get_database_url(self) -> str:
        """Build database connection string from secrets."""
        user = self.require("POSTGRES_USER")
        password = self.require("POSTGRES_PASSWORD")
        host = self.require("POSTGRES_HOST")
        port = self.get("POSTGRES_PORT", "5432")
        db = self.get("POSTGRES_DB", "trading_journal")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@lru_cache(maxsize=1)
def get_secrets_manager(environment: str = None) -> SecretsManager:
    """Get singleton secrets manager instance."""
    if environment is None:
        environment = os.getenv("ENVIRONMENT", "development")
    return SecretsManager(environment)
