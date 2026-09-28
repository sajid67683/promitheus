from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from backend.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}

    kwargs = {"pool_pre_ping": True, "connect_args": {"connect_timeout": 10}}
    if settings.on_vercel:
        # Serverless instances come and go; don't hold idle connections open.
        # Point DATABASE_URL at your provider's pooled endpoint (e.g. Neon "-pooler").
        kwargs["poolclass"] = NullPool
    return kwargs


_url = settings.database_url
engine = create_engine(_url, **_engine_kwargs(_url))
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
