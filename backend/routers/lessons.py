from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from backend.database import get_db
from backend import models
from backend.deps import get_current_user

router = APIRouter(prefix="/lessons", tags=["Lessons"])


@router.get("/")
def get_all_lessons(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fetches all lessons belonging to the user's uploaded materials."""
    lessons = (
        db.query(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.SourceMaterial.user_id == current_user.id)
        .order_by(models.Lesson.id)
        .all()
    )

    return [
        {
            "id": lesson.id,
            "title": lesson.title,
            "material_id": lesson.material_id,
            "is_completed": lesson.is_completed,
            "unit_number": lesson.unit_number,
            "unit_title": lesson.material.title
        }
        for lesson in lessons
    ]


@router.get("/{lesson_id}")
def get_lesson_with_questions(lesson_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Fetches a specific lesson and its generated questions."""
    lesson = (
        db.query(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.Lesson.id == lesson_id)
        .filter(models.SourceMaterial.user_id == current_user.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    questions = db.query(models.Question).filter(
        models.Question.lesson_id == lesson_id).all()

    return {
        "questions": [
            {"question_id": q.id, "type": q.question_type, "data": q.content}
            for q in questions
        ]
    }

# --- ✨ THE ULTIMATE COMPLETION ENGINE ✨ ---


@router.post("/{lesson_id}/complete")
def complete_lesson(lesson_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Marks a lesson completed and calculates the Fire Streak!"""
    lesson = (
        db.query(models.Lesson)
        .join(models.SourceMaterial)
        .filter(models.Lesson.id == lesson_id)
        .filter(models.SourceMaterial.user_id == current_user.id)
        .first()
    )

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found.")

    # 1. Mark the lesson finished
    lesson.is_completed = True

    # 2. 🔥 SMART STREAK & DAILY RESET LOGIC
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # Initializing values if they are None (CRITICAL for new users)
    if current_user.streak is None:
        current_user.streak = 0
    if current_user.daily_lessons is None:
        current_user.daily_lessons = 0

    # LOGIC: If the user has a 0 streak, we force it to 1 on the very first lesson.
    if current_user.streak == 0:
        current_user.streak = 1
        current_user.last_active_date = today

    # Otherwise, if it's a new day, check if the streak continues or resets
    elif current_user.last_active_date != today:
        if current_user.last_active_date == yesterday:
            current_user.streak += 1
        else:
            current_user.streak = 1

        # Reset Daily Quests for the new day
        current_user.daily_xp = 0
        current_user.daily_lessons = 0
        current_user.last_active_date = today

    # Increment daily lesson count (for Quest 2)
    current_user.daily_lessons += 1

    db.commit()
    return {
        "status": "success",
        "message": "Lesson completed!",
        "new_streak": current_user.streak
    }
