import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers import auth, cron, lessons, pages, upload, users
from backend.routers.pages import FRONTEND_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Fail at startup (with a clear message) if required settings are missing.
settings.validate()

app = FastAPI(
    title="Promitheus API",
    description="The backend engine for turning lectures into interactive lessons.",
    version="2.0.0",
    # Interactive API docs only outside production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(lessons.router)
app.include_router(users.router)
app.include_router(cron.router)
app.include_router(pages.router)

# On Vercel this directory is promoted to the CDN at build time.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
