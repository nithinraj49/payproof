"""Verifies a Firebase ID token on every protected route.

The user id always comes from the verified token, never from the path or body
(REQUIREMENTS.md section 10).
"""
from typing import Optional

import firebase_admin
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth

from backend.errors import ApiError

_bearer = HTTPBearer(auto_error=False)

if not firebase_admin._apps:
    firebase_admin.initialize_app()


async def require_user_id(request: Request) -> str:
    credentials: Optional[HTTPAuthorizationCredentials] = await _bearer(request)
    if credentials is None or not credentials.credentials:
        raise ApiError(401, "missing_token", "Sign-in required.")
    try:
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except Exception:
        raise ApiError(401, "invalid_token", "Sign-in session expired or invalid.")
    return decoded["uid"]
