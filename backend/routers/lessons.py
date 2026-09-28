"""Quizzes: lesson and practice attempts, server-side grading, results and question reports.

Flow: POST /lessons/{id}/attempts or /practice/attempts -> questions without answers
      POST /attempts/{id}/answers  -> server grades one answer, reveals the solution
      POST /attempts/{id}/complete -> server awards XP / streak / quests, returns a review
"""
import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import ai_service, gamification, grading, models, services
from backend.config import settings
from backend.database import get_db
from backend.deps import get_current_user, get_today
from backend.schemas import AnswerRequest, ReportRequest

router = APIRouter(tags=["Lessons"])

PRACTICE_SIZE = 10


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


def _owned_question(db: Session, question_id: int, user: models.User) -> models.Question:
    question = (
        db.query(models.Question)
        .join(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.Question.id == question_id, models.SourceMaterial.user_id == user.id)
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    return question


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


def _attempt_payload(attempt: models.LessonAttempt, questions: list[models.Question], title: str) -> dict:
    return {
        "attempt_id": attempt.id,
        "kind": attempt.kind,
        "lesson_title": title,
        "questions": [grading.public_question(q) for q in questions],
    }


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
    questions = lesson.visible_questions
    if not questions:
        raise HTTPException(status_code=404, detail="This lesson has no questions left.")

    attempt = models.LessonAttempt(
        user_id=user.id, lesson_id=lesson.id, kind="lesson", question_ids=[q.id for q in questions]
    )
    db.add(attempt)
    db.commit()
    return _attempt_payload(attempt, questions, lesson.title)


@router.post("/practice/attempts")
def start_practice(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    mistakes = [question for _, question in services.open_mistakes(db, user)]
    if not mistakes:
        raise HTTPException(status_code=404, detail="No mistakes to practice. Nice work!")
    chosen = random.sample(mistakes, min(PRACTICE_SIZE, len(mistakes)))

    attempt = models.LessonAttempt(user_id=user.id, kind="practice", question_ids=[q.id for q in chosen])
    db.add(attempt)
    db.commit()
    return _attempt_payload(attempt, chosen, "Practice your mistakes")


def _grade_text_with_ai(db: Session, user: models.User, question: models.Question, answer: str) -> bool | None:
    """Second opinion for free-recall answers that didn't match. None = no AI verdict."""
    if services.ai_gradings_last_day(db, user.id) >= settings.daily_ai_grading_limit:
        return None
    try:
        return ai_service.check_equivalent(
            question.content.get("prompt", ""), grading.accepted_answers(question), answer
        )
    except ai_service.AIServiceError:
        return None


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
    if body.question_id not in (attempt.question_ids or []):
        raise HTTPException(status_code=404, detail="Question not found.")
    question = db.get(models.Question, body.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")

    already = db.query(models.AttemptAnswer.id).filter_by(attempt_id=attempt.id, question_id=question.id).first()
    if already:
        raise HTTPException(status_code=409, detail="You already answered this question.")

    feedback, typo, used_ai = "", False, False
    qtype = question.question_type
    if qtype in grading.AI_TYPES:
        if not isinstance(body.answer, str) or not body.answer.strip():
            raise HTTPException(status_code=400, detail="Write an answer first.")
        if services.ai_gradings_last_day(db, user.id) >= settings.daily_ai_grading_limit:
            raise HTTPException(status_code=429, detail="You've reached today's AI grading limit. Try again tomorrow.")
        db.commit()  # release the DB connection while waiting on the AI
        try:
            is_correct, feedback = ai_service.grade_explanation(
                question.content.get("prompt", ""), question.content.get("answer", ""), body.answer
            )
        except ai_service.AIServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        used_ai = True
    else:
        match = grading.grade_locally(question, body.answer)
        is_correct, typo = match.correct, match.typo
        if not is_correct and qtype in grading.TEXT_TYPES and isinstance(body.answer, str) and body.answer.strip():
            user_id = user.id
            db.commit()
            verdict = _grade_text_with_ai(db, db.get(models.User, user_id), question, body.answer)
            if verdict is not None:
                used_ai = True
                is_correct = verdict

    db.add(
        models.AttemptAnswer(
            attempt_id=attempt_id,
            question_id=question.id,
            is_correct=is_correct,
            given_answer=body.answer,
            used_ai=used_ai,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already answered this question.")
    return {
        "correct": is_correct,
        "typo": typo,
        "correct_answer": grading.display_answer(question),
        "explanation": question.content.get("explanation", ""),
        "feedback": feedback,
    }


def _review(db: Session, attempt: models.LessonAttempt) -> list[dict]:
    answers = {a.question_id: a for a in attempt.answers}
    questions = {q.id: q for q in db.query(models.Question).filter(models.Question.id.in_(attempt.question_ids or []))}
    review = []
    for qid in attempt.question_ids or []:
        answer, question = answers.get(qid), questions.get(qid)
        if answer is None or question is None or answer.is_correct:
            continue
        given = answer.given_answer
        review.append(
            {
                "question_id": qid,
                "type": question.question_type,
                "prompt": question.content.get("prompt", ""),
                "your_answer": " ".join(given) if isinstance(given, list) else (given or ""),
                "correct_answer": grading.display_answer(question),
                "explanation": question.content.get("explanation", ""),
            }
        )
    return review


@router.post("/attempts/{attempt_id}/complete")
def complete_attempt(
    attempt_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    attempt = _owned_attempt(db, attempt_id, user, lock=True)
    lesson = None
    streak_before = gamification.effective_streak(user, today)
    goal_reached_before = gamification.effective_daily(user, today)[0] >= gamification.daily_goal(user)

    if attempt.completed_at is None:
        if attempt.kind == "lesson":
            if attempt.lesson_id is None:
                raise HTTPException(status_code=404, detail="This lesson no longer exists.")
            # Lock the lesson and user rows so a double-submit can't award XP twice.
            lesson = _owned_lesson(db, attempt.lesson_id, user, lock=True)
        db.refresh(user, with_for_update=True)

        answers = db.query(models.AttemptAnswer).filter_by(attempt_id=attempt.id).all()
        answered = {a.question_id for a in answers}
        hidden = {
            qid
            for (qid,) in db.query(models.Question.id).filter(
                models.Question.id.in_(attempt.question_ids or []), models.Question.hidden.is_(True)
            )
        }
        missing = [qid for qid in attempt.question_ids or [] if qid not in answered and qid not in hidden]
        if missing:
            raise HTTPException(status_code=400, detail="Answer every question before finishing.")

        correct_ids = [a.question_id for a in answers if a.is_correct]
        if attempt.kind == "lesson":
            # XP only the first time a lesson is completed; replays are practice.
            xp = len(correct_ids) * gamification.XP_PER_CORRECT_ANSWER if not lesson.is_completed else 0
        else:
            fixed = services.fixed_before(db, user, correct_ids, exclude_attempt=attempt.id)
            xp = len([q for q in correct_ids if q not in fixed]) * gamification.XP_PER_FIXED_MISTAKE

        gamification.record_lesson_completion(user, today, xp)
        now = gamification.now_utc()
        if lesson is not None:
            lesson.is_completed = True
            lesson.completed_at = lesson.completed_at or now
        attempt.completed_at = now
        attempt.completed_on = today
        attempt.correct_count = len(correct_ids)
        attempt.xp_awarded = xp
        db.commit()

    if attempt.lesson_id is not None and lesson is None:
        lesson = db.get(models.Lesson, attempt.lesson_id)
    next_lesson_id = None
    if lesson is not None:
        following = [
            l for l in lesson.material.lessons if l.order_in_unit > lesson.order_in_unit and not l.is_completed
        ]
        next_lesson_id = following[0].id if following else None

    daily_xp, _ = gamification.effective_daily(user, today)
    started, finished = attempt.started_at, attempt.completed_at
    duration = int((finished - started).total_seconds()) if started and finished and started.tzinfo == finished.tzinfo else None
    streak_after = gamification.effective_streak(user, today)
    return {
        "kind": attempt.kind,
        "xp_awarded": attempt.xp_awarded,
        "correct": attempt.correct_count,
        "total": len(attempt.question_ids or []),
        "streak": streak_after,
        "streak_extended": streak_after > streak_before,
        "daily_xp": daily_xp,
        "daily_goal": gamification.daily_goal(user),
        "goal_reached_now": not goal_reached_before and daily_xp >= gamification.daily_goal(user),
        "duration_seconds": duration,
        "next_lesson_id": next_lesson_id,
        "mistakes": _review(db, attempt),
    }


@router.post("/questions/{question_id}/report")
def report_question(
    question_id: int,
    body: ReportRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    question = _owned_question(db, question_id, user)
    db.add(models.QuestionReport(user_id=user.id, question_id=question.id, reason=body.reason, details=body.details))
    result = {"status": "ok", "accepted": False, "hidden": False}

    if body.reason == "accept_my_answer":
        query = (
            db.query(models.AttemptAnswer)
            .join(models.LessonAttempt)
            .filter(models.LessonAttempt.user_id == user.id, models.AttemptAnswer.question_id == question.id)
        )
        if body.attempt_id is not None:
            query = query.filter(models.AttemptAnswer.attempt_id == body.attempt_id)
        answer = query.order_by(models.AttemptAnswer.id.desc()).first()
        if answer is None or answer.is_correct:
            raise HTTPException(status_code=400, detail="There's no wrong answer to accept for this question.")
        # No XP, but it stops counting as a mistake and is accepted next time.
        answer.accepted_by_user = True
        if question.question_type in grading.TEXT_TYPES and isinstance(answer.given_answer, str):
            content = dict(question.content)
            alternatives = list(content.get("alternatives", []))
            if answer.given_answer.strip() and answer.given_answer.strip() not in alternatives:
                alternatives.append(answer.given_answer.strip()[:200])
            content["alternatives"] = alternatives[:20]
            question.content = content
        result["accepted"] = True
    elif body.reason == "wrong_or_unclear":
        question.hidden = True
        result["hidden"] = True

    db.commit()
    return result
