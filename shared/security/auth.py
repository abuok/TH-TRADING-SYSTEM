"""
shared/security/auth.py
-----------------------
Centralized authentication logic for microservice protection.
"""

import base64
import os
from fastapi import HTTPException, Request

def verify_auth(request: Request):
    """
    Verifies HTTP Basic Auth if enabled via ENVIRONMENT variable.
    Default credentials: admin / admin (or via DASHBOARD_USER / DASHBOARD_PASS)
    """
    if not os.getenv("DASHBOARD_AUTH_ENABLED", "false").lower() == "true":
        return True

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        scheme, credentials = auth_header.split()
        if scheme.lower() != "basic":
            raise ValueError()
        decoded = base64.b64decode(credentials).decode("ascii")
        username, _, password = decoded.partition(":")
        
        expected_user = os.getenv("DASHBOARD_USER", "admin")
        expected_pass = os.getenv("DASHBOARD_PASS", "admin")
        
        if username != expected_user or password != expected_pass:
            raise ValueError()
            
    except Exception:
        raise HTTPException(
            status_code=401, 
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        ) from None
        
    return username
