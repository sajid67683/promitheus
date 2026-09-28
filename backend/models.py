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

    # --- PROFILE & PREFERENCES ---
    # DiceBear avatar as "style:seed"; NULL means the default derived from the username.
    avatar = Column(String(80), nullable=True)
    daily_xp_goal = Column(Integer, nullable=False, default=50, server_default=text("50"))
    # IANA timezone reported by the browser; decides when "today" starts.
    timezone = Column(String(64), nullable=False, default="UTC", server_default=text("'UTC'"))
    onboarded = Column(Boolean, nullable=False, default=False, server_default=false())
    # Bumped on password change / "sign out everywhere" to invalidate old sessions.
    token_version = _counter()

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
    lessons = relationship(
        "Lesson", back_populates="material", cascade="all, delete-orphan", order_by="Lesson.order_in_unit"
    )


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

    @property
    def visible_questions(self):
        return [q for q in self.questions if not q.hidden]


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    question_type = Column(String(30), nullable=False)
    # prompt / options / chunks / answer / alternatives / explanation.
    # The answer never leaves the server before the question is answered.
    content = Column(JSONType, nullable=False)
    # Hidden by the learner (reported as wrong or unclear); skipped in future quizzes.
    hidden = Column(Boolean, nullable=False, default=False, server_default=false())

    lesson = relationship("Lesson", back_populates="questions")


class LessonAttempt(Base):
    """One run through a quiz (a lesson, or a practice set of past mistakes)."""

    __tablename__ = "lesson_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # "lesson" or "practice"
    kind = Column(String(20), nullable=False, default="lesson", server_default=text("'lesson'"))
    # Kept (as NULL) when the lesson is deleted, so activity history survives.
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
    # The exact questions in this attempt, in order.
    question_ids = Column(JSONType, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Completion day in the user's timezone (drives the activity calendar).
    completed_on = Column(Date, nullable=True, index=True)
    correct_count = _counter()
    xp_awarded = _counter()

    answers = relationship("AttemptAnswer", back_populates="attempt", cascade="all, delete-orphan")


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(
        Integer, ForeignKey("lesson_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    is_correct = Column(Boolean, nullable=False)
    # What the learner submitted, for the mistakes review.
    given_answer = Column(JSONType, nullable=True)
    # The learner said "my answer should be accepted": no longer a mistake, but no XP either.
    accepted_by_user = Column(Boolean, nullable=False, default=False, server_default=false())
    used_ai = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    attempt = relationship("LessonAttempt", back_populates="answers")

    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),)


class QuestionReport(Base):
    __tablename__ = "question_reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    # "accept_my_answer" | "wrong_or_unclear" | "other"
    reason = Column(String(40), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # SHA-256 of the token; the token itself only exists in the email.
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class AIUsage(Base):
    """One row per quiz generation, for per-user daily limits that survive deletions."""

    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # "generate"
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class LeagueReset(Base):
    """One row per processed week, so the weekly cron can't run twice for the same week."""

    __tablename__ = "league_resets"

    week_key = Column(String(10), primary_key=True)  # ISO week, e.g. "2026-W39"
    ran_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    promoted = _counter()
    demoted = _counter()
