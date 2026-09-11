import secrets
from typing import Optional

from fastapi import HTTPException, Request, status
from starlette.responses import RedirectResponse

from app.config import Settings

SESSION_USER_KEY = "user"


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    """Compare submitted credentials to configured demo credentials."""

    return secrets.compare_digest(username, settings.app_admin_username) and secrets.compare_digest(
        password, settings.app_admin_password
    )


def login_user(request: Request, username: str) -> None:
    request.session[SESSION_USER_KEY] = username


def logout_user(request: Request) -> None:
    request.session.clear()


def current_user(request: Request) -> Optional[str]:
    user = request.session.get(SESSION_USER_KEY)
    return user if isinstance(user, str) else None


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    return user


def redirect_if_anonymous(request: Request) -> Optional[RedirectResponse]:
    if current_user(request):
        return None
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
