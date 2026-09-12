from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import Settings, get_settings

SESSION_USER_KEY = "username"
SESSION_SALT = "prism-fastapi-demo-session"


def verify_credentials(username: str, password: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return secrets.compare_digest(username, settings.app_admin_username) and secrets.compare_digest(
        password, settings.app_admin_password
    )


def _serializer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt=SESSION_SALT)


def issue_session(response: Response, username: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    token = _serializer(settings).dumps({SESSION_USER_KEY: username})
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 8,
    )


def clear_session(response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    response.delete_cookie(settings.session_cookie_name)


def read_session(request: Request, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    try:
        data = _serializer(settings).loads(token)
    except BadSignature:
        return None
    if not isinstance(data, dict) or not data.get(SESSION_USER_KEY):
        return None
    return data


def require_user(request: Request, settings: Settings | None = None) -> str:
    data = read_session(request, settings)
    if not data:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return str(data[SESSION_USER_KEY])
