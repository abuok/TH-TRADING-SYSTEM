"""
JWT-based API authentication for service-to-service communication.

Provides token generation, validation, and FastAPI dependency injection.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthCredentials, HTTPBearer

from .secrets_manager import get_secrets_manager


class JWTAuthenticator:
    """JWT token generation and validation."""

    def __init__(self, secret_key: str | None = None, algorithm: str = "HS256"):
        """Initialize JWT authenticator.

        Args:
            secret_key: Secret key for signing tokens (if None, loads from secrets manager)
            algorithm: JWT algorithm (default HS256)
        """
        if secret_key is None:
            secrets = get_secrets_manager()
            secret_key = secrets.get("JWT_SECRET_KEY") or secrets.get("API_SECRET_KEY")
            if not secret_key:
                raise ValueError("JWT_SECRET_KEY or API_SECRET_KEY not configured")

        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_token(
        self,
        subject: str,
        service: str,
        expires_in_minutes: int = 60,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Create a JWT token.

        Args:
            subject: Token subject (usually service name)
            service: Service name issuing the token
            expires_in_minutes: Token expiration time in minutes
            additional_claims: Additional data to include in token

        Returns:
            Encoded JWT token
        """
        to_encode = {
            "sub": subject,
            "service": service,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            "type": "bearer",
        }

        if additional_claims:
            to_encode.update(additional_claims)

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return str(encoded_jwt)

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return dict(payload)
        except jwt.ExpiredSignatureError as e:
            raise ValueError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}") from e

    def verify_service_token(
        self, token: str, allowed_services: list | None = None
    ) -> dict[str, Any]:
        """Verify token and optionally check service authorization.

        Args:
            token: JWT token string
            allowed_services: List of allowed service names (if None, any service allowed)

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is invalid or service not authorized
        """
        payload = self.verify_token(token)

        if allowed_services and payload.get("service") not in allowed_services:
            raise ValueError(f"Service '{payload.get('service')}' not authorized")

        return payload


# FastAPI dependency for route protection
security = HTTPBearer()


async def verify_api_token(
    credentials: HTTPAuthCredentials = Depends(security),
) -> dict[str, Any]:
    """FastAPI dependency to verify JWT token in Authorization header.

    Usage:
        @app.get("/protected")
        async def protected_route(token_data: Dict = Depends(verify_api_token)):
            return {"service": token_data["service"]}
    """
    try:
        authenticator = get_jwt_authenticator()
        token_data = authenticator.verify_token(credentials.credentials)
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def verify_service_token(
    service_name: str,
    credentials: HTTPAuthCredentials = Depends(security),
) -> dict[str, Any]:
    """FastAPI dependency to verify token from specific service.

    Usage:
        @app.get("/admin")
        async def admin_route(token_data: Dict = Depends(lambda creds: verify_service_token("orchestration", creds))):
            return {"authorized": True}
    """
    try:
        authenticator = get_jwt_authenticator()
        token_data = authenticator.verify_service_token(
            credentials.credentials,
            allowed_services=[service_name],
        )
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@lru_cache(maxsize=1)
def get_jwt_authenticator() -> JWTAuthenticator:
    """Get singleton JWT authenticator instance."""
    return JWTAuthenticator()
