import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.config import settings
from backend.database import get_db
from backend.schemas import GoogleLoginRequest, LoginRequest, RegisterRequest
from backend.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_response(user: models.User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "username": user.username,
    }


def _username_taken(db: Session, username: str) -> bool:
    return (
        db.query(models.User.id).filter(func.lower(models.User.username) == username.lower()).first()
        is not None
    )


def _email_taken(db: Session, email: str) -> bool:
    return db.query(models.User.id).filter(models.User.email == email).first() is not None


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if _username_taken(db, data.username):
        raise HTTPException(status_code=400, detail="That username is already taken.")
    if _email_taken(db, data.email):
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    user = models.User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Someone registered the same name/email a moment ago.
        db.rollback()
        raise HTTPException(status_code=400, detail="That username or email is already taken.")
    db.refresh(user)
    return _token_response(user)


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    identifier = data.username.strip()
    query = db.query(models.User)
    if "@" in identifier:
        user = query.filter(models.User.email == identifier.lower()).first()
    else:
        user = query.filter(func.lower(models.User.username) == identifier.lower()).first()

    if not verify_password(data.password, user.hashed_password if user else None) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    return _token_response(user)


def _username_from_google(db: Session, name: str | None, email: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]", "", (name or "").replace(" ", "_"))[:24]
    if len(base) < 3:
        base = re.sub(r"[^A-Za-z0-9_.-]", "", email.split("@")[0])[:24]
    if len(base) < 3:
        base = "learner"

    candidate = base
    for _ in range(20):
        if not _username_taken(db, candidate):
            return candidate
        candidate = f"{base}{secrets.randbelow(10_000):04d}"
    return f"learner{secrets.token_hex(4)}"


@router.post("/google")
def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    try:
        idinfo = id_token.verify_oauth2_token(
            data.credential, google_requests.Request(), settings.google_client_id
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in. Please try again.")

    google_sub = idinfo.get("sub")
    email = (idinfo.get("email") or "").lower()
    if not google_sub or not email or not idinfo.get("email_verified"):
        raise HTTPException(status_code=401, detail="Your Google account email is not verified.")

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
            raise HTTPException(status_code=409, detail="Could not create your account. Please try again.")
        db.refresh(user)

    return _token_response(user)
