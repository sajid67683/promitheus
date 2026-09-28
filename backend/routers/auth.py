import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .. import models, auth, database

router = APIRouter(prefix="/auth", tags=["Authentication"])

# --- DATA MODELS (The "Forms") ---


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class GoogleToken(BaseModel):
    credential: str

# --- ROUTES ---


@router.post("/register")
def register(user_data: UserCreate, db: Session = Depends(database.get_db)):
    # 1. Check if username is taken
    existing_user = db.query(models.User).filter(
        models.User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    # 2. DEBUG PRINT: See what is actually arriving
    print(f"--- REGISTRATION DEBUG ---")
    print(f"Received password: {user_data.password}")
    print(f"Password Length: {len(user_data.password)} bytes")

    # 3. Hash the password (Passing ONLY the string)
    try:
        hashed_pass = auth.get_password_hash(user_data.password)
    except Exception as e:
        print(f"HASHING FAILED: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Security Error: {str(e)}")

    # 4. Create and save the new user
    new_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pass
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User created successfully! Please login."}


@router.post("/login")
def login(login_data: UserLogin, db: Session = Depends(database.get_db)):
    # 1. Find user by username
    user = db.query(models.User).filter(
        models.User.username == login_data.username).first()

    # 2. Verify password
    if not user or not auth.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # 3. Generate the "Key" (JWT Token)
    access_token = auth.create_access_token(data={"sub": user.username})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }


# --- NEW GOOGLE LOGIN ROUTE ---

@router.post("/google")
def google_login(token: GoogleToken, db: Session = Depends(database.get_db)):
    try:
        # 1. Verify the Google Token
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        if not client_id:
            raise HTTPException(
                status_code=500, detail="Google Client ID missing from .env")

        idinfo = id_token.verify_oauth2_token(
            token.credential,
            google_requests.Request(),
            client_id
        )

        # 2. Extract user info
        email = idinfo.get('email')
        # Fallback to email prefix if no name
        name = idinfo.get('name', email.split('@')[0])

        # 3. Check if user already exists (checking both email and username just in case)
        user = db.query(models.User).filter(
            (models.User.email == email) | (models.User.username == email)
        ).first()

        # 4. If they are new, create their Promitheus account!
        if not user:
            # Generate a secure random dummy password
            dummy_pwd = secrets.token_urlsafe(32)
            hashed_pass = auth.get_password_hash(dummy_pwd)

            user = models.User(
                username=name,  # Using their Google name or email prefix
                email=email,
                hashed_password=hashed_pass,
                xp=0,              # Ensure these default stats match your models.py
                streak=0,
                daily_xp=0,
                daily_lessons=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # 5. Issue your standard Promitheus JWT
        access_token = auth.create_access_token(data={"sub": user.username})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "username": user.username
        }

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        print(f"Google Login Error: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error during Google Login")
