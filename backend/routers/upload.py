import io
import logging
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import ai_service, gamification, models
from backend.config import settings
from backend.database import get_db
from backend.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def _split_filename(filename: str | None) -> tuple[str, str]:
    # Some browsers send a full path; keep only the file's own name.
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name, ""
    return stem, "." + ext.lower()


def _extract_text(data: bytes, extension: str) -> str:
    if extension == ".txt":
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="Could not read this text file. Save it as UTF-8 and try again.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(status_code=400, detail="This PDF is password-protected.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except HTTPException:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Could not read this PDF. It may be damaged.")
    except Exception:
        logger.exception("Unexpected PDF parsing error")
        raise HTTPException(status_code=400, detail="Could not read this PDF.")


@router.post("/lecture")
def upload_lecture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stem, extension = _split_filename(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload a .pdf or .txt file.")

    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File is too large (max {limit_mb} MB).")

    since = gamification.now_utc() - timedelta(days=1)
    uploads_today = (
        db.query(func.count(models.SourceMaterial.id))
        .filter(models.SourceMaterial.user_id == user.id, models.SourceMaterial.created_at >= since)
        .scalar()
    )
    if uploads_today >= settings.daily_upload_limit:
        raise HTTPException(status_code=429, detail="Daily upload limit reached. Try again tomorrow.")
    user_id = user.id
    # End the transaction so no DB connection sits idle during the (slow) AI call.
    db.commit()

    text = _extract_text(data, extension)
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No readable text found. Scanned PDFs (images of pages) aren't supported yet.",
        )

    try:
        sections = ai_service.generate_learning_content(text)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    material = models.SourceMaterial(user_id=user_id, title=(stem or "Untitled lecture")[:255], raw_text=text)
    db.add(material)
    total_questions = 0
    for order, (title, qtype, questions) in enumerate(sections, start=1):
        lesson = models.Lesson(title=title, order_in_unit=order)
        material.lessons.append(lesson)
        for content in questions:
            lesson.questions.append(models.Question(question_type=qtype, content=content))
        total_questions += len(questions)
    db.commit()

    return {"status": "success", "message": f"Unit created with {total_questions} questions!"}
