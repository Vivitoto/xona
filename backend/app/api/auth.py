from __future__ import annotations

import hashlib
from typing import Any

import bcrypt
from fastapi import APIRouter, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel

from backend.app.core.secrets import ensure_app_secret
from backend.app.core.settings import Settings

COOKIE_NAME = "xona_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
SESSION_SALT = "xona-session"

router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordHasher:
    def __init__(self, *, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, password: str) -> str:
        password_bytes = password.encode("utf-8")
        hashed_password = bcrypt.hashpw(
            password_bytes, bcrypt.gensalt(rounds=self._rounds)
        )
        return hashed_password.decode("utf-8")

    def verify(self, password: str, password_hash: str | None) -> bool:
        if not password_hash:
            return False

        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except ValueError:
            return False


def authenticated_username(request: Request, settings: Settings) -> str | None:
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie:
        return None

    serializer = _session_serializer(settings)
    try:
        payload = serializer.loads(session_cookie, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    username = payload.get("username")
    if username != settings.auth_username:
        return None

    return username if isinstance(username, str) else None


@router.post("/login")
def login(
    credentials: LoginRequest, request: Request, response: Response
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    configured_username = settings.auth_username
    username_matches = (
        configured_username is not None and credentials.username == configured_username
    )
    password_matches = PasswordHasher().verify(
        credentials.password, settings.auth_password_hash
    )

    if not settings.auth_enabled or not username_matches or not password_matches:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"detail": "Invalid credentials"}

    session_cookie = _session_serializer(settings).dumps(
        {"username": configured_username}
    )
    response.set_cookie(
        COOKIE_NAME,
        session_cookie,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="Lax",
    )
    return {"authenticated": True, "username": configured_username}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    settings: Settings = request.app.state.settings
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="Lax",
    )
    return {"authenticated": False}


@router.get("/status")
def status_endpoint(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    username = (
        authenticated_username(request, settings) if settings.auth_enabled else None
    )
    if username is None:
        return {"authenticated": False}
    return {"authenticated": True, "username": username}


def _session_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=ensure_app_secret(settings.config_dir),
        salt=SESSION_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )
