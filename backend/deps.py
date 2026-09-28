from datetime import date

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend import models
from backend.database import get_db
from backend.gamification import user_today
from backend.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(models.User, user_id)
    if user is None:
        raise unauthorized
    return user


def get_today(x_timezone: str | None = Header(default=None)) -> date:
    """Today in the browser's timezone (the frontend sends an X-Timezone header)."""
    return user_today(x_timezone)
