"""Password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from backend.config import settings

ALGORITHM = "HS256"

# Used to keep login timing the same whether or not the username exists.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    # Schemas reject passwords over bcrypt's 72-byte limit, so nothing is silently truncated.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str | None) -> bool:
    """Pass hashed_password=None for unknown users; it still spends the bcrypt time."""
    try:
        matches = bcrypt.checkpw(password.encode("utf-8"), (hashed_password or _DUMMY_HASH).encode("utf-8"))
    except ValueError:  # e.g. password longer than 72 bytes
        return False
    return matches and hashed_password is not None


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Returns the user id, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
