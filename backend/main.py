import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import settings
from backend.routers import auth, cron, lessons, materials, pages, upload, users
from backend.routers.pages import FRONTEND_DIR, LoginRequired, login_redirect, templates

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Fail at startup (with a clear message) if required settings are missing.
settings.validate()

app = FastAPI(
    title="Promitheus API",
    description="The backend engine for turning lectures into interactive lessons.",
    version="3.0.0",
    # Interactive API docs only outside production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(lessons.router)
app.include_router(materials.router)
app.include_router(users.router)
app.include_router(cron.router)
app.include_router(pages.router)

app.add_exception_handler(LoginRequired, login_redirect)


@app.exception_handler(StarletteHTTPException)
async def friendly_404(request: Request, exc: StarletteHTTPException):
    # Browsers get a real page; API clients keep the JSON error.
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(request, "404.html", {"settings": settings, "user": None}, status_code=404)
    return await http_exception_handler(request, exc)


# On Vercel this directory is promoted to the CDN at build time.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
