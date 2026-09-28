import io
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from backend import models, services
from backend.config import settings
from backend.database import get_db
from backend.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
SAMPLE_LECTURE = Path(__file__).resolve().parents[1] / "sample_lecture.txt"


def _split_filename(filename: str | None) -> tuple[str, str]:
    # Some browsers send a full path; keep only the file's own name.
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name, ""
    return stem, "." + ext.lower()


def _pretty_title(stem: str) -> str:
    title = re.sub(r"[_\s]+", " ", stem).strip()
    return (title[:1].upper() + title[1:]) if title else "Untitled lecture"


def _extract_text(data: bytes, extension: str) -> str:
    if extension == ".txt":
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="Couldn't read this text file. Save it as UTF-8 and try again.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(status_code=400, detail="This PDF is password-protected. Remove the password and try again.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except HTTPException:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Couldn't read this PDF. It may be damaged.")
    except Exception:
        logger.exception("Unexpected PDF parsing error")
        raise HTTPException(status_code=400, detail="Couldn't read this PDF.")


def _create_unit(db: Session, user_id: int, title: str, text: str) -> dict:
    unit = services.generate_unit(db, user_id, text)
    material = models.SourceMaterial(user_id=user_id, title=(unit.title or title)[:255], raw_text=text)
    services.fill_material(material, unit)
    db.add(material)
    db.commit()
    first_lesson = material.lessons[0].id if material.lessons else None
    return {
        "status": "success",
        "material_id": material.id,
        "first_lesson_id": first_lesson,
        "title": material.title,
        "message": f"“{material.title}” is ready with {unit.question_count} questions.",
    }


@router.post("/lecture")
def upload_lecture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stem, extension = _split_filename(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="That file type isn't supported. Upload a PDF or a .txt file.")

    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"That file is larger than {limit_mb} MB. Try a smaller file.")

    user_id = user.id
    services.ensure_generation_allowed(db, user_id)
    text = _extract_text(data, extension)
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No readable text found. Scanned PDFs (photos of pages) aren't supported yet.",
        )
    return _create_unit(db, user_id, _pretty_title(stem), text)


@router.post("/sample")
def upload_sample(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Builds a unit from a bundled sample lecture, for trying the app without a file."""
    return _create_unit(db, user.id, "Photosynthesis", SAMPLE_LECTURE.read_text(encoding="utf-8"))
