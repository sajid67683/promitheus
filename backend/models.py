from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .database import Base

# JSONB on PostgreSQL, plain JSON elsewhere (lets the test suite run on SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _counter():
    return Column(Integer, nullable=False, default=0, server_default=text("0"))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(30), nullable=False, unique=True)
    # Stored lower-cased.
    email = Column(String(254), nullable=False, unique=True)
    # NULL for accounts that only sign in with Google.
    hashed_password = Column(String(100), nullable=True)
    google_sub = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # --- LIFETIME STATS ---
    xp = _counter()
    streak = _counter()
    # The last calendar day (in the user's timezone) a lesson was completed.
    last_lesson_date = Column(Date, nullable=True)

    # --- DAILY STATS (only valid while stats_date is today) ---
    daily_xp = _counter()
    daily_lessons = _counter()
    stats_date = Column(Date, nullable=True)

    # --- WEEKLY STATS (reset by the weekly league cron) ---
    weekly_xp = _counter()
    # Paper -> Iron -> Bronze -> Silver -> Gold -> Platinum -> Diamond
    league = Column(String(20), nullable=False, default="Paper", server_default=text("'Paper'"))

    # --- QUESTS ---
    quests_completed = _counter()
    month_quests = _counter()
    quest_month = Column(String(7), nullable=True)  # "YYYY-MM" that month_quests belongs to

    materials = relationship("SourceMaterial", back_populates="owner", cascade="all, delete-orphan")

    __table_args__ = (
        # Usernames are unique regardless of case ("Sajid" and "sajid" can't both exist).
        Index("ix_users_username_lower", func.lower(username), unique=True),
    )


class SourceMaterial(Base):
    __tablename__ = "source_materials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    owner = relationship("User", back_populates="materials")
    lessons = relationship("Lesson", back_populates="material", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    material_id = Column(
        Integer, ForeignKey("source_materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(100), nullable=False)
    order_in_unit = Column(Integer, nullable=False, default=1, server_default=text("1"))
    is_completed = Column(Boolean, nullable=False, default=False, server_default=false())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    material = relationship("SourceMaterial", back_populates="lessons")
    questions = relationship(
        "Question", back_populates="lesson", cascade="all, delete-orphan", order_by="Question.id"
    )


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    question_type = Column(String(30), nullable=False)
    # prompt / options / chunks / answer. The answer never leaves the server.
    content = Column(JSONType, nullable=False)

    lesson = relationship("Lesson", back_populates="questions")


class LessonAttempt(Base):
    """One run through a lesson's quiz. Answers are graded and recorded server-side."""

    __tablename__ = "lesson_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    correct_count = _counter()
    xp_awarded = _counter()

    answers = relationship("AttemptAnswer", back_populates="attempt", cascade="all, delete-orphan")


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(
        Integer, ForeignKey("lesson_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    used_ai = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    attempt = relationship("LessonAttempt", back_populates="answers")

    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),)


class LeagueReset(Base):
    """One row per processed week, so the weekly cron can't run twice for the same week."""

    __tablename__ = "league_resets"

    week_key = Column(String(10), primary_key=True)  # ISO week, e.g. "2026-W39"
    ran_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    promoted = _counter()
    demoted = _counter()
