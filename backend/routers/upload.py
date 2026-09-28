from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import fitz
from backend.database import get_db
from backend import models, ai_service
from backend.deps import get_current_user

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/lecture")
async def upload_lecture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    content = await file.read()
    text = ""

    try:
        if file.filename.endswith(".pdf"):
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                text += page.get_text()
        elif file.filename.endswith(".txt"):
            text = content.decode("utf-8")
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported file type.")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"File reading error: {str(e)}")

    if not text.strip():
        raise HTTPException(
            status_code=400, detail="The uploaded file seems to be empty.")

    new_material = models.SourceMaterial(
        user_id=current_user.id,
        title=file.filename,
        raw_text=text
    )
    db.add(new_material)
    db.flush()  # Flush gets the ID without committing permanently

    try:
        ai_data = ai_service.generate_learning_content(text)

        # 🌟 THE FIX: Map exactly to the 6 new keys the AI is generating
        sections = [
            ("Free Recall", ai_data.get('level_1_short_answer', [])),
            ("Fill in the Blanks", ai_data.get('level_2_fill_blank', [])),
            ("Multiple Choice", ai_data.get('level_3_mcq', [])),
            ("True or False", ai_data.get('level_4_true_false', [])),
            ("Rearrange Concepts", ai_data.get(
                'level_5_rearrange', [])),  # <-- NEW LEVEL
            ("Explain Concepts", ai_data.get('level_6_explain', []))
        ]

        # 🛡️ THE SAFETY CHECK: Make sure we actually extracted questions!
        total_questions = sum(len(q_list) for _, q_list in sections)
        if total_questions == 0:
            raise ValueError(
                "The AI generated the lesson but failed to format the questions correctly. Please try again.")

        for i, (sec_title, q_list) in enumerate(sections):
            # 1. Create the Section Node
            new_lesson = models.Lesson(
                material_id=new_material.id,
                title=sec_title,
                unit_number=new_material.id,
                order_in_unit=i + 1
            )
            db.add(new_lesson)
            db.flush()

            # 2. Add all questions for this specific level
            for q in q_list:
                new_question = models.Question(
                    lesson_id=new_lesson.id,
                    question_type=q.get('type', 'multiple_choice'),
                    content=q
                )
                db.add(new_question)

        db.commit()

        return {"status": "success", "message": f"Unit created with {total_questions} total questions!"}

    except Exception as e:
        db.rollback()  # If anything fails, undo the whole database transaction!
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")
