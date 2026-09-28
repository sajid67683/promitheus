"""Library, practice, settings, onboarding and reporting support

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _to_date(value):
    if value is None:
        return None
    if isinstance(value, str):  # SQLite returns timestamps as text
        return date.fromisoformat(value[:10])
    return value.date()


def upgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("daily_xp_goal", sa.Integer(), nullable=False, server_default=sa.text("50")))
        batch.add_column(sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'UTC'")))
        batch.add_column(sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")))
    # Everyone who signed up before onboarding existed has already found their way around.
    op.execute("UPDATE users SET onboarded = true")

    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("lesson_attempts") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default=sa.text("'lesson'")))
        batch.add_column(sa.Column("question_ids", JSON_TYPE, nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("completed_on", sa.Date(), nullable=True))
        batch.alter_column("lesson_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_lesson_attempts_completed_on", "lesson_attempts", ["completed_on"])
    if is_postgres:
        # Keep attempt history when a lesson is deleted.
        op.drop_constraint("lesson_attempts_lesson_id_fkey", "lesson_attempts", type_="foreignkey")
        op.create_foreign_key(
            "lesson_attempts_lesson_id_fkey", "lesson_attempts", "lessons", ["lesson_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("attempt_answers") as batch:
        batch.add_column(sa.Column("given_answer", JSON_TYPE, nullable=True))
        batch.add_column(sa.Column("accepted_by_user", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_attempt_answers_question_id", "attempt_answers", ["question_id"])

    # Backfill existing attempts: their question set and completion day.
    bind = op.get_bind()
    attempts = bind.execute(sa.text("SELECT id, lesson_id, completed_at FROM lesson_attempts")).fetchall()
    for attempt_id, lesson_id, completed_at in attempts:
        ids = [
            row[0]
            for row in bind.execute(
                sa.text("SELECT id FROM questions WHERE lesson_id = :lid ORDER BY id"), {"lid": lesson_id}
            )
        ]
        bind.execute(
            sa.text("UPDATE lesson_attempts SET question_ids = :ids, completed_on = :day WHERE id = :id").bindparams(
                sa.bindparam("ids", type_=JSON_TYPE)
            ),
            {"ids": ids, "day": _to_date(completed_at), "id": attempt_id},
        )

    op.create_table(
        "question_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_question_reports_user_id", "question_reports", ["user_id"])
    op.create_index("ix_question_reports_question_id", "question_reports", ["question_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_user_id", "ai_usage", ["user_id"])
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("password_reset_tokens")
    op.drop_table("question_reports")
    op.drop_index("ix_attempt_answers_question_id", table_name="attempt_answers")
    with op.batch_alter_table("attempt_answers") as batch:
        batch.drop_column("accepted_by_user")
        batch.drop_column("given_answer")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("lesson_attempts_lesson_id_fkey", "lesson_attempts", type_="foreignkey")
        op.create_foreign_key(
            "lesson_attempts_lesson_id_fkey", "lesson_attempts", "lessons", ["lesson_id"], ["id"], ondelete="CASCADE"
        )
    op.drop_index("ix_lesson_attempts_completed_on", table_name="lesson_attempts")
    op.execute("DELETE FROM lesson_attempts WHERE lesson_id IS NULL")
    with op.batch_alter_table("lesson_attempts") as batch:
        batch.alter_column("lesson_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("completed_on")
        batch.drop_column("question_ids")
        batch.drop_column("kind")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("hidden")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
        batch.drop_column("onboarded")
        batch.drop_column("timezone")
        batch.drop_column("daily_xp_goal")
        batch.drop_column("avatar")
