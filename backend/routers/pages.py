"""Server-rendered HTML pages. JavaScript only adds interaction on top."""
import calendar
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import gamification, models, services
from backend.config import settings
from backend.database import get_db
from backend.deps import get_optional_user
from backend.routers.users import leaderboard, stats

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")
templates.env.globals["LEAGUE_ORDER"] = gamification.LEAGUE_ORDER
templates.env.filters["shortdate"] = lambda d: f"{d:%b} {d.day}, {d.year}"
templates.env.filters["monthname"] = lambda d: f"{d:%B} {d.year}"

router = APIRouter(include_in_schema=False)

GET = ["GET", "HEAD"]  # HEAD for uptime monitors and link previews


class LoginRequired(Exception):
    def __init__(self, next_path: str):
        self.next_path = next_path


def _safe_next(path: str | None) -> str:
    # Only same-site relative paths, never "//evil.com".
    if path and path.startswith("/") and not path.startswith("//"):
        return path
    return "/dashboard"


def _require_user(request: Request, user: models.User | None) -> models.User:
    if user is None:
        raise LoginRequired(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
    return user


def _render(request: Request, name: str, user: models.User | None = None, **context):
    base = {"settings": settings, "user": user, "active": context.pop("active", None)}
    if user is not None:
        today = gamification.user_today(user.timezone)
        base["me"] = stats(user, today)
        base["today"] = today
    return templates.TemplateResponse(request, name, {**base, **context})


def _app_page(request: Request, user: models.User | None, name: str, **context):
    user = _require_user(request, user)
    if not user.onboarded and request.url.path != "/welcome":
        return RedirectResponse("/welcome", status_code=303)
    return _render(request, name, user, **context)


# ---------- public ----------

@router.api_route("/", methods=GET)
def landing(request: Request, user: models.User | None = Depends(get_optional_user)):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return _render(request, "landing.html")


@router.api_route("/login", methods=GET)
def login(request: Request, next: str | None = None, user: models.User | None = Depends(get_optional_user)):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _render(request, "auth.html", mode="login", next_path=_safe_next(next))


@router.api_route("/signup", methods=GET)
def signup(request: Request, user: models.User | None = Depends(get_optional_user)):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return _render(request, "auth.html", mode="signup", next_path="/welcome")


@router.api_route("/forgot-password", methods=GET)
def forgot_password(request: Request):
    return _render(request, "forgot_password.html")


@router.api_route("/reset-password", methods=GET)
def reset_password(request: Request, token: str = ""):
    return _render(request, "reset_password.html", token=token)


# ---------- app ----------

@router.api_route("/welcome", methods=GET)
def welcome(request: Request, user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    return _render(request, "welcome.html", user, goal_options=gamification.DAILY_GOAL_OPTIONS)


@router.api_route("/dashboard", methods=GET)
def dashboard(request: Request, db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    units = services.unit_views(db, user)
    mistakes = sum(unit.mistakes for unit in units)
    return _app_page(request, user, "dashboard.html", active="learn", units=units, mistake_count=mistakes)


@router.api_route("/quiz/{lesson_id}", methods=GET)
def quiz(request: Request, lesson_id: int, user: models.User | None = Depends(get_optional_user)):
    return _app_page(request, user, "quiz.html", mode="lesson", lesson_id=lesson_id)


@router.api_route("/practice/session", methods=GET)
def practice_session(request: Request, user: models.User | None = Depends(get_optional_user)):
    return _app_page(request, user, "quiz.html", mode="practice", lesson_id=None)


@router.api_route("/practice", methods=GET)
def practice(request: Request, db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    rows = services.open_mistakes(db, user)
    mistakes = []
    for answer, question in rows:
        given = answer.given_answer
        mistakes.append(
            {
                "prompt": question.content.get("prompt", ""),
                "unit": question.lesson.material.title,
                "lesson": question.lesson.title,
                "your_answer": " ".join(given) if isinstance(given, list) else (given or ""),
                "correct_answer": " ".join(question.content["answer"])
                if isinstance(question.content.get("answer"), list)
                else question.content.get("answer", ""),
                "explanation": question.content.get("explanation", ""),
            }
        )
    return _app_page(request, user, "practice.html", active="practice", mistakes=mistakes)


@router.api_route("/library", methods=GET)
def library(request: Request, db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    return _app_page(
        request,
        user,
        "library.html",
        active="library",
        units=services.unit_views(db, user),
        uploads_left=max(0, settings.daily_upload_limit - services.generations_last_day(db, user.id)),
    )


@router.api_route("/leaderboard", methods=GET)
def leaderboard_page(request: Request, db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    board = leaderboard(db, user, gamification.user_today(user.timezone))
    return _app_page(request, user, "leaderboard.html", active="leagues", board=board)


@router.api_route("/quests", methods=GET)
def quests(request: Request, user: models.User | None = Depends(get_optional_user)):
    return _app_page(request, user, "quests.html", active="quests")


@router.api_route("/streaks", methods=GET)
def streaks(
    request: Request,
    month: str | None = None,
    db: Session = Depends(get_db),
    user: models.User | None = Depends(get_optional_user),
):
    user = _require_user(request, user)
    today = gamification.user_today(user.timezone)
    try:
        year, mon = (int(part) for part in (month or "").split("-"))
        first = date(year, mon, 1)
    except ValueError:
        first = today.replace(day=1)
    days_in_month = calendar.monthrange(first.year, first.month)[1]
    last = first.replace(day=days_in_month)
    active_days = services.activity_days(db, user, first, last)
    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = last + timedelta(days=1)
    return _app_page(
        request,
        user,
        "streaks.html",
        active="profile",
        month_start=first,
        days_in_month=days_in_month,
        leading_blanks=(first.weekday() + 1) % 7,  # calendar starts on Sunday
        active_days=active_days,
        active_count=len(active_days),
        prev_month=prev_month.strftime("%Y-%m"),
        next_month=next_month.strftime("%Y-%m") if next_month <= today else None,
    )


@router.api_route("/profile", methods=GET)
def profile(request: Request, db: Session = Depends(get_db), user: models.User | None = Depends(get_optional_user)):
    user = _require_user(request, user)
    units = services.unit_views(db, user)
    return _app_page(
        request,
        user,
        "profile.html",
        active="profile",
        unit_count=len(units),
        lessons_done=sum(unit.completed for unit in units),
    )


@router.api_route("/settings", methods=GET)
def settings_page(request: Request, user: models.User | None = Depends(get_optional_user)):
    return _app_page(
        request,
        user,
        "settings.html",
        active="settings",
        goal_options=gamification.DAILY_GOAL_OPTIONS,
        avatar_styles=services.AVATAR_STYLES,
    )


# Old URLs, kept so existing bookmarks still work.
@router.api_route("/users/leaderboard", methods=GET)
def old_leaderboard():
    return RedirectResponse("/leaderboard", status_code=301)


@router.api_route("/users/profile", methods=GET)
def old_profile():
    return RedirectResponse("/profile", status_code=301)


@router.api_route("/favicon.ico", methods=GET)
def favicon():
    return FileResponse(FRONTEND_DIR / "static" / "assets" / "favicon.ico")


def login_redirect(request: Request, exc: LoginRequired):
    return RedirectResponse(f"/login?next={quote(exc.next_path)}", status_code=303)
