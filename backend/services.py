"""Domain logic shared by the JSON API and the server-rendered pages."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import ai_service, gamification, models
from backend.config import settings


# ---------- AI usage limits ----------

def _since_yesterday():
    return gamification.now_utc() - timedelta(days=1)


def generations_last_day(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(models.AIUsage.id))
        .filter(models.AIUsage.user_id == user_id, models.AIUsage.created_at >= _since_yesterday())
        .scalar()
    )


def ensure_generation_allowed(db: Session, user_id: int) -> None:
    if generations_last_day(db, user_id) >= settings.daily_upload_limit:
        raise HTTPException(
            status_code=429,
            detail=f"You've reached today's limit of {settings.daily_upload_limit} generated units. Try again tomorrow.",
        )


def ai_gradings_last_day(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(models.AttemptAnswer.id))
        .join(models.LessonAttempt)
        .filter(
            models.LessonAttempt.user_id == user_id,
            models.AttemptAnswer.used_ai.is_(True),
            models.AttemptAnswer.created_at >= _since_yesterday(),
        )
        .scalar()
    )


def generate_unit(db: Session, user_id: int, text: str) -> ai_service.GeneratedUnit:
    """Runs the AI with limits applied. The DB transaction is closed during the slow call."""
    ensure_generation_allowed(db, user_id)
    db.commit()
    try:
        unit = ai_service.generate_learning_content(text)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    db.add(models.AIUsage(user_id=user_id, kind="generate"))
    return unit


def fill_material(material: models.SourceMaterial, unit: ai_service.GeneratedUnit) -> None:
    for order, (title, qtype, questions) in enumerate(unit.sections, start=1):
        if not questions:
            continue
        lesson = models.Lesson(title=title, order_in_unit=order)
        material.lessons.append(lesson)
        for content in questions:
            lesson.questions.append(models.Question(question_type=qtype, content=content))


# ---------- progress ----------

@dataclass
class LessonView:
    id: int
    title: str
    order: int
    is_completed: bool
    state: str  # "done" | "current" | "locked"
    question_count: int


@dataclass
class UnitView:
    id: int
    title: str
    created_at: object
    lessons: list[LessonView] = field(default_factory=list)
    mistakes: int = 0

    @property
    def completed(self) -> int:
        return sum(1 for lesson in self.lessons if lesson.is_completed)

    @property
    def total(self) -> int:
        return len(self.lessons)

    @property
    def question_count(self) -> int:
        return sum(lesson.question_count for lesson in self.lessons)

    @property
    def next_lesson(self) -> LessonView | None:
        return next((lesson for lesson in self.lessons if lesson.state == "current"), None)


def unit_views(db: Session, user: models.User) -> list[UnitView]:
    materials = (
        db.query(models.SourceMaterial)
        .filter(models.SourceMaterial.user_id == user.id)
        .order_by(models.SourceMaterial.id)
        .all()
    )
    mistakes_by_material: dict[int, int] = {}
    for _, question in open_mistakes(db, user):
        mid = question.lesson.material_id
        mistakes_by_material[mid] = mistakes_by_material.get(mid, 0) + 1

    views = []
    for material in materials:
        unit = UnitView(material.id, material.title, material.created_at, mistakes=mistakes_by_material.get(material.id, 0))
        previous_done = True
        for lesson in material.lessons:
            if lesson.is_completed:
                state = "done"
            elif previous_done:
                state = "current"
            else:
                state = "locked"
            unit.lessons.append(
                LessonView(lesson.id, lesson.title, lesson.order_in_unit, lesson.is_completed, state, len(lesson.visible_questions))
            )
            previous_done = lesson.is_completed
        views.append(unit)
    return views


def open_mistakes(db: Session, user: models.User) -> list[tuple[models.AttemptAnswer, models.Question]]:
    """Questions whose most recent answer was wrong (and not accepted by the learner)."""
    latest = (
        db.query(func.max(models.AttemptAnswer.id).label("id"))
        .join(models.LessonAttempt)
        .filter(models.LessonAttempt.user_id == user.id)
        .group_by(models.AttemptAnswer.question_id)
        .subquery()
    )
    rows = (
        db.query(models.AttemptAnswer, models.Question)
        .join(latest, latest.c.id == models.AttemptAnswer.id)
        .join(models.Question, models.Question.id == models.AttemptAnswer.question_id)
        .filter(
            models.AttemptAnswer.is_correct.is_(False),
            models.AttemptAnswer.accepted_by_user.is_(False),
            models.Question.hidden.is_(False),
        )
        .order_by(models.AttemptAnswer.id.desc())
        .all()
    )
    return rows


def activity_days(db: Session, user: models.User, start: date, end: date) -> set[date]:
    rows = (
        db.query(models.LessonAttempt.completed_on)
        .filter(
            models.LessonAttempt.user_id == user.id,
            models.LessonAttempt.completed_on.isnot(None),
            models.LessonAttempt.completed_on >= start,
            models.LessonAttempt.completed_on <= end,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def fixed_before(db: Session, user: models.User, question_ids: list[int], exclude_attempt: int) -> set[int]:
    """Questions already fixed in an earlier completed practice session (they don't pay XP twice)."""
    if not question_ids:
        return set()
    rows = (
        db.query(models.AttemptAnswer.question_id)
        .join(models.LessonAttempt)
        .filter(
            models.LessonAttempt.user_id == user.id,
            models.LessonAttempt.kind == "practice",
            models.LessonAttempt.completed_at.isnot(None),
            models.LessonAttempt.id != exclude_attempt,
            models.AttemptAnswer.is_correct.is_(True),
            models.AttemptAnswer.question_id.in_(question_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


# ---------- avatars ----------

AVATAR_STYLES = ["bottts", "adventurer", "fun-emoji", "lorelei", "thumbs", "pixel-art"]


def avatar_url(user: models.User, size: int = 96) -> str:
    style, _, seed = (user.avatar or "").partition(":")
    if style not in AVATAR_STYLES or not seed:
        style, seed = "bottts", user.username.replace(".", "-")
    from urllib.parse import quote

    return f"https://api.dicebear.com/9.x/{style}/svg?seed={quote(seed)}&size={size}&radius=50&backgroundColor=d7cffc,ffd9bf,c7f0d8"
