from datetime import date
from urllib.parse import unquote, urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend import models
from backend.config import settings
from backend.database import get_db
from backend.gamification import user_today, valid_timezone
from backend.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def verify_same_origin(request: Request) -> None:
    """CSRF defence for state-changing requests, on top of SameSite=Lax cookies.

    Browsers always send Origin (or at least Referer) on cross-site POSTs, so a request
    that names another site is rejected. Non-browser clients send neither and pass.
    """
    if request.method in SAFE_METHODS:
        return
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return
    if urlsplit(source).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail="Cross-site request blocked.")


def browser_timezone(request: Request) -> str | None:
    """X-Timezone header (API calls) or the tz cookie set by app.js (page loads)."""
    tz = request.headers.get("x-timezone") or unquote(request.cookies.get("tz", ""))
    return tz if valid_timezone(tz) else None


def _token_from_request(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials is not None:
        return credentials.credentials
    return request.cookies.get(settings.session_cookie)


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User | None:
    token = _token_from_request(request, credentials)
    if not token:
        return None
    decoded = decode_access_token(token)
    if decoded is None:
        return None
    user_id, version = decoded
    user = db.get(models.User, user_id)
    if user is None or user.token_version != version:
        return None

    # Remember the browser's timezone so server-rendered pages agree with the client.
    tz = browser_timezone(request)
    if tz and tz != user.timezone:
        user.timezone = tz
        db.commit()
    return user


def get_current_user(
    request: Request,
    user: models.User | None = Depends(get_optional_user),
) -> models.User:
    verify_same_origin(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_today(request: Request, user: models.User | None = Depends(get_optional_user)) -> date:
    """Today in the user's timezone: the browser's X-Timezone header, else the stored one."""
    tz = browser_timezone(request)
    if tz is None and user is not None:
        tz = user.timezone
    return user_today(tz)
