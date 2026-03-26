"""Security module for credential and authentication management.

Submodule imports are intentionally deferred to avoid optional heavy
dependencies (e.g. PyJWT, cryptography) being required at module-load
time in environments where only rate_limiting is needed.

Import sub-modules directly, e.g.:
    from shared.security.rate_limiting import limiter, setup_rate_limiting
    from shared.security.auth import JWTAuthenticator
"""

__all__ = [
    "limiter",
    "setup_rate_limiting",
    "LIMITS",
]
