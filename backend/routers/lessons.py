"""Lessons and quiz attempts.

Flow: POST /lessons/{id}/attempts -> questions without answers
      POST /attempts/{id}/answers  -> server grades one answer
      POST /attempts/{id}/complete -> server awards XP / streak / quests
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import ai_service, gamification, grading, models
from backend.config import settings
from backend.database import get_db
from backend.deps import get_current_user, get_today
from backend.schemas import AnswerRequest

router = APIRouter(tags=["Lessons"])


def _owned_lesson(db: Session, lesson_id: int, user: models.User, lock: bool = False) -> models.Lesson:
    query = (
        db.query(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.Lesson.id == lesson_id, models.SourceMaterial.user_id == user.id)
    )
    if lock:
        query = query.with_for_update(of=models.Lesson)
    lesson = query.first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found.")
    return lesson


def _owned_attempt(db: Session, attempt_id: int, user: models.User, lock: bool = False) -> models.LessonAttempt:
    query = db.query(models.LessonAttempt).filter(
        models.LessonAttempt.id == attempt_id, models.LessonAttempt.user_id == user.id
    )
    if lock:
        query = query.with_for_update()
    attempt = query.first()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return attempt


@router.get("/lessons/")
def list_lessons(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    lessons = (
        db.query(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.SourceMaterial.user_id == user.id)
        .order_by(models.SourceMaterial.id, models.Lesson.order_in_unit, models.Lesson.id)
        .all()
    )
    return [
        {
            "id": lesson.id,
            "title": lesson.title,
            "material_id": lesson.material_id,
            "unit_title": lesson.material.title,
            "is_completed": lesson.is_completed,
        }
        for lesson in lessons
    ]


@router.post("/lessons/{lesson_id}/attempts")
def start_attempt(lesson_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    lesson = _owned_lesson(db, lesson_id, user)
    if not lesson.questions:
        raise HTTPException(status_code=404, detail="This lesson has no questions.")

    attempt = models.LessonAttempt(user_id=user.id, lesson_id=lesson.id)
    db.add(attempt)
    db.commit()
    return {
        "attempt_id": attempt.id,
        "lesson_title": lesson.title,
        "questions": [grading.public_question(q) for q in lesson.questions],
    }


def _ai_gradings_today(db: Session, user: models.User) -> int:
    since = gamification.now_utc() - timedelta(days=1)
    return (
        db.query(func.count(models.AttemptAnswer.id))
        .join(models.LessonAttempt)
        .filter(
            models.LessonAttempt.user_id == user.id,
            models.AttemptAnswer.used_ai.is_(True),
            models.AttemptAnswer.created_at >= since,
        )
        .scalar()
    )


@router.post("/attempts/{attempt_id}/answers")
def submit_answer(
    attempt_id: int,
    body: AnswerRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    attempt = _owned_attempt(db, attempt_id, user)
    if attempt.completed_at is not None:
        raise HTTPException(status_code=409, detail="This quiz is already finished.")

    question = db.get(models.Question, body.question_id)
    if question is None or question.lesson_id != attempt.lesson_id:
        raise HTTPException(status_code=404, detail="Question not found.")

    already = (
        db.query(models.AttemptAnswer.id)
        .filter_by(attempt_id=attempt.id, question_id=question.id)
        .first()
    )
    if already:
        raise HTTPException(status_code=409, detail="You already answered this question.")

    feedback = ""
    used_ai = question.question_type in grading.AI_TYPES
    if used_ai:
        if not isinstance(body.answer, str) or not body.answer.strip():
            raise HTTPException(status_code=400, detail="Please write an answer first.")
        if _ai_gradings_today(db, user) >= settings.daily_ai_grading_limit:
            raise HTTPException(status_code=429, detail="Daily AI grading limit reached. Try again tomorrow.")
        # Release the DB connection while waiting on the AI.
        db.commit()
        try:
            is_correct, feedback = ai_service.grade_explanation(
                question.content.get("prompt", ""),
                question.content.get("answer", ""),
                body.answer,
            )
        except ai_service.AIServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    else:
        is_correct = grading.grade_locally(question, body.answer)

    db.add(
        models.AttemptAnswer(
            attempt_id=attempt_id, question_id=question.id, is_correct=is_correct, used_ai=used_ai
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already answered this question.")
    return {
        "correct": is_correct,
        "correct_answer": grading.display_answer(question),
        "feedback": feedback,
    }


@router.post("/attempts/{attempt_id}/complete")
def complete_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    attempt = _owned_attempt(db, attempt_id, user, lock=True)

    if attempt.completed_at is None:
        # Lock the lesson and user rows so a double-submit can't award XP twice.
        lesson = _owned_lesson(db, attempt.lesson_id, user, lock=True)
        db.refresh(user, with_for_update=True)

        total = db.query(func.count(models.Question.id)).filter_by(lesson_id=lesson.id).scalar()
        answers = db.query(models.AttemptAnswer).filter_by(attempt_id=attempt.id).all()
        if len(answers) < total:
            raise HTTPException(status_code=400, detail="Answer every question before finishing.")

        correct = sum(1 for a in answers if a.is_correct)
        # XP is only awarded the first time a lesson is completed; replays are practice.
        first_completion = not lesson.is_completed
        xp = correct * gamification.XP_PER_CORRECT_ANSWER if first_completion else 0

        gamification.record_lesson_completion(user, today, xp)
        now = gamification.now_utc()
        lesson.is_completed = True
        lesson.completed_at = lesson.completed_at or now
        attempt.completed_at = now
        attempt.correct_count = correct
        attempt.xp_awarded = xp
        db.commit()

    total = len(attempt.answers)
    return {
        "xp_awarded": attempt.xp_awarded,
        "correct": attempt.correct_count,
        "total": total,
        "streak": gamification.effective_streak(user, today),
    }
