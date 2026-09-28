import logging
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import gamification, mailer, models
from backend.config import settings
from backend.database import get_db
from backend.deps import verify_same_origin
from backend.schemas import (
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from backend.security import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    hash_token,
    new_reset_token,
    set_session_cookie,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"], dependencies=[Depends(verify_same_origin)])

RESET_TOKEN_LIFETIME = timedelta(hours=1)


def _start_session(response: Response, user: models.User) -> dict:
    token = create_access_token(user.id, user.token_version)
    set_session_cookie(response, token)
    return {
        # Also returned for API clients; the web app relies on the HttpOnly cookie.
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "next": "/dashboard" if user.onboarded else "/welcome",
    }


def username_taken(db: Session, username: str, exclude_id: int | None = None) -> bool:
    query = db.query(models.User.id).filter(func.lower(models.User.username) == username.lower())
    if exclude_id is not None:
        query = query.filter(models.User.id != exclude_id)
    return query.first() is not None


def _email_taken(db: Session, email: str) -> bool:
    return db.query(models.User.id).filter(models.User.email == email).first() is not None


@router.post("/register")
def register(data: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if username_taken(db, data.username):
        raise HTTPException(status_code=400, detail="That username is already taken.")
    if _email_taken(db, data.email):
        raise HTTPException(status_code=400, detail="An account with that email already exists. Log in instead.")

    user = models.User(username=data.username, email=data.email, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Someone registered the same name/email a moment ago.
        db.rollback()
        raise HTTPException(status_code=400, detail="That username or email is already taken.")
    db.refresh(user)
    return _start_session(response, user)


@router.post("/login")
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    identifier = data.username.strip()
    query = db.query(models.User)
    if "@" in identifier:
        user = query.filter(models.User.email == identifier.lower()).first()
    else:
        user = query.filter(func.lower(models.User.username) == identifier.lower()).first()

    if not verify_password(data.password, user.hashed_password if user else None) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That username or password is incorrect.",
        )
    return _start_session(response, user)


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"status": "ok"}


def _username_from_google(db: Session, name: str | None, email: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]", "", (name or "").replace(" ", "_"))[:24]
    if len(base) < 3:
        base = re.sub(r"[^A-Za-z0-9_.-]", "", email.split("@")[0])[:24]
    if len(base) < 3:
        base = "learner"

    candidate = base
    for _ in range(20):
        if not username_taken(db, candidate):
            return candidate
        candidate = f"{base}{secrets.randbelow(10_000):04d}"
    return f"learner{secrets.token_hex(4)}"


@router.post("/google")
def google_login(data: GoogleLoginRequest, response: Response, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    try:
        idinfo = id_token.verify_oauth2_token(data.credential, google_requests.Request(), settings.google_client_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Try again.")

    google_sub = idinfo.get("sub")
    email = (idinfo.get("email") or "").lower()
    if not google_sub or not email or not idinfo.get("email_verified"):
        raise HTTPException(status_code=401, detail="Your Google account email isn't verified.")

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()
    if user is None:
        if _email_taken(db, email):
            # Don't auto-link: the existing account's email was never verified, so linking
            # would let whoever registered it first get into this Google user's account.
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Log in with your username and password.",
            )
        user = models.User(
            username=_username_from_google(db, idinfo.get("name"), email),
            email=email,
            google_sub=google_sub,
            hashed_password=None,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.warning("Google sign-up collided with an existing account")
            raise HTTPException(status_code=409, detail="Could not create your account. Try again.")
        db.refresh(user)

    return _start_session(response, user)


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    # Same response whether or not the email exists, so this can't be used to find accounts.
    generic = {"status": "ok", "message": "If that email has an account, a reset link is on its way."}
    email = data.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        return generic

    token, token_hash = new_reset_token()
    db.add(
        models.PasswordResetToken(
            user_id=user.id, token_hash=token_hash, expires_at=gamification.now_utc() + RESET_TOKEN_LIFETIME
        )
    )
    db.commit()
    base = settings.app_url or str(request.base_url).rstrip("/")
    mailer.send_password_reset(user.email, user.username, f"{base}/reset-password?token={token}")
    return generic


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, response: Response, db: Session = Depends(get_db)):
    record = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == hash_token(data.token))
        .with_for_update()
        .first()
    )
    now = gamification.now_utc()
    expires_at = record.expires_at if record else None
    if expires_at is not None and expires_at.tzinfo is None:  # SQLite drops timezones
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    if record is None or record.used_at is not None or expires_at < now:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    user = db.get(models.User, record.user_id)
    user.hashed_password = hash_password(data.password)
    user.token_version += 1  # sign out every other session
    record.used_at = now
    db.commit()
    return _start_session(response, user)
