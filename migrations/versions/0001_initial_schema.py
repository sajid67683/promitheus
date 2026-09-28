"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _counter(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0"))


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("hashed_password", sa.String(length=100), nullable=True),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _counter("xp"),
        _counter("streak"),
        sa.Column("last_lesson_date", sa.Date(), nullable=True),
        _counter("daily_xp"),
        _counter("daily_lessons"),
        sa.Column("stats_date", sa.Date(), nullable=True),
        _counter("weekly_xp"),
        sa.Column("league", sa.String(length=20), nullable=False, server_default=sa.text("'Paper'")),
        _counter("quests_completed"),
        _counter("month_quests"),
        sa.Column("quest_month", sa.String(length=7), nullable=True),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_index("ix_users_username_lower", "users", [sa.text("lower(username)")], unique=True)

    op.create_table(
        "source_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_materials_user_id", "source_materials", ["user_id"])

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "material_id", sa.Integer(), sa.ForeignKey("source_materials.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("order_in_unit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lessons_material_id", "lessons", ["material_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("content", JSON_TYPE, nullable=False),
    )
    op.create_index("ix_questions_lesson_id", "questions", ["lesson_id"])

    op.create_table(
        "lesson_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _counter("correct_count"),
        _counter("xp_awarded"),
    )
    op.create_index("ix_lesson_attempts_user_id", "lesson_attempts", ["user_id"])
    op.create_index("ix_lesson_attempts_lesson_id", "lesson_attempts", ["lesson_id"])

    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id", sa.Integer(), sa.ForeignKey("lesson_attempts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("used_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
    )
    op.create_index("ix_attempt_answers_attempt_id", "attempt_answers", ["attempt_id"])

    op.create_table(
        "league_resets",
        sa.Column("week_key", sa.String(length=10), primary_key=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _counter("promoted"),
        _counter("demoted"),
    )


def downgrade() -> None:
    op.drop_table("league_resets")
    op.drop_table("attempt_answers")
    op.drop_table("lesson_attempts")
    op.drop_table("questions")
    op.drop_table("lessons")
    op.drop_table("source_materials")
    op.drop_index("ix_users_username_lower", table_name="users")
    op.drop_table("users")
