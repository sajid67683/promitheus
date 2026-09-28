"""Request bodies. Validation here is the first line of defence against bad input."""
import re

from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.fullmatch(v):
            raise ValueError("Username must be 3-30 characters: letters, numbers, '_', '.' or '-'.")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 254 or not EMAIL_RE.fullmatch(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return v


class LoginRequest(BaseModel):
    # Username or email.
    username: str = Field(max_length=254)
    password: str = Field(max_length=200)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(max_length=10_000)


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
