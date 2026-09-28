"""HTML pages. They carry no user data; the browser fetches it from the API with its token."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.config import settings

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")

router = APIRouter(include_in_schema=False)


def _render(request: Request, name: str, **context):
    return templates.TemplateResponse(request, name, context)


@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request):
    return _render(request, "dashboard.html")


@router.get("/quiz/{lesson_id}")
def quiz(request: Request, lesson_id: int):
    return _render(request, "quiz.html", lesson_id=lesson_id)


@router.get("/quests")
def quests(request: Request):
    return _render(request, "quests.html")


@router.get("/streaks")
def streaks(request: Request):
    return _render(request, "streaks.html")


@router.get("/leaderboard")
def leaderboard(request: Request):
    return _render(request, "leaderboard.html")


@router.get("/profile")
def profile(request: Request):
    return _render(request, "profile.html")


@router.get("/login")
def login(request: Request):
    return _render(request, "login.html", google_client_id=settings.google_client_id)


# Old URLs, kept so existing bookmarks still work.
@router.get("/users/leaderboard")
def old_leaderboard():
    return RedirectResponse("/leaderboard", status_code=301)


@router.get("/users/profile")
def old_profile():
    return RedirectResponse("/profile", status_code=301)


@router.get("/favicon.ico")
def favicon():
    return FileResponse(FRONTEND_DIR / "static" / "assets" / "favicon.ico")
