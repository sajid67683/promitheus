"""Request bodies. Validation here is the first line of defence against bad input."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_username(v: str) -> str:
    v = v.strip()
    if not USERNAME_RE.fullmatch(v):
        raise ValueError("Username must be 3-30 characters: letters, numbers, '_', '.' or '-'.")
    return v


def _check_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    return v


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.fullmatch(v):
        raise ValueError("Enter a valid email address.")
    return v


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        return _check_username(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _check_email(v)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _check_password(v)


class LoginRequest(BaseModel):
    # Username or email.
    username: str = Field(max_length=254)
    password: str = Field(max_length=200)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(max_length=10_000)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(max_length=200)
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _check_password(v)


class ChangePasswordRequest(BaseModel):
    # Required when the account already has a password; Google-only accounts can set one.
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _check_password(v)


class ProfileUpdate(BaseModel):
    username: str | None = None
    avatar: str | None = Field(default=None, max_length=80)
    daily_xp_goal: int | None = None
    onboarded: bool | None = None

    @field_validator("username")
    @classmethod
    def check_username(cls, v):
        return None if v is None else _check_username(v)

    @field_validator("avatar")
    @classmethod
    def check_avatar(cls, v):
        if v is None:
            return v
        style, sep, seed = v.partition(":")
        if not sep or not re.fullmatch(r"[a-z-]{2,20}", style) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", seed):
            raise ValueError("Pick one of the avatars shown.")
        return v


class DeleteAccountRequest(BaseModel):
    # Typing the username confirms the user really means it.
    confirm_username: str = Field(max_length=30)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Give the unit a name.")
        return v


class ReportRequest(BaseModel):
    reason: Literal["accept_my_answer", "wrong_or_unclear", "other"]
    details: str | None = Field(default=None, max_length=1000)
    attempt_id: int | None = None


class AnswerRequest(BaseModel):
    question_id: int
    # A string for most question types, a list of chunks for "rearrange".
    answer: str | list[str]

    @field_validator("answer")
    @classmethod
    def limit_size(cls, v):
        if isinstance(v, str):
            if len(v) > 2000:
                raise ValueError("Answer is too long (2000 characters max).")
        else:
            if len(v) > 20 or any(len(chunk) > 500 for chunk in v):
                raise ValueError("Answer is too long.")
        return v
