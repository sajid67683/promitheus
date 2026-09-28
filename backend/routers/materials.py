"""Library management: rename, delete and regenerate uploaded units."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import models, services
from backend.database import get_db
from backend.deps import get_current_user
from backend.schemas import RenameRequest

router = APIRouter(prefix="/materials", tags=["Library"])


def _owned_material(db: Session, material_id: int, user: models.User) -> models.SourceMaterial:
    material = (
        db.query(models.SourceMaterial)
        .filter(models.SourceMaterial.id == material_id, models.SourceMaterial.user_id == user.id)
        .first()
    )
    if material is None:
        raise HTTPException(status_code=404, detail="Unit not found.")
    return material


@router.patch("/{material_id}")
def rename_material(
    material_id: int, body: RenameRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    material = _owned_material(db, material_id, user)
    material.title = body.title
    db.commit()
    return {"id": material.id, "title": material.title}


@router.delete("/{material_id}")
def delete_material(material_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    material = _owned_material(db, material_id, user)
    # Lessons and questions go with it; XP already earned and activity history stay.
    db.delete(material)
    db.commit()
    return {"status": "deleted"}


@router.post("/{material_id}/regenerate")
def regenerate_material(
    material_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    """Builds a fresh set of questions from the same lecture text. Lesson progress starts over."""
    material = _owned_material(db, material_id, user)
    user_id, text = user.id, material.raw_text
    unit = services.generate_unit(db, user_id, text)

    material = _owned_material(db, material_id, db.get(models.User, user_id))
    for lesson in list(material.lessons):
        db.delete(lesson)
    db.flush()
    material.lessons = []
    services.fill_material(material, unit)
    db.commit()
    return {
        "status": "success",
        "message": f"“{material.title}” now has {unit.question_count} new questions.",
        "first_lesson_id": material.lessons[0].id if material.lessons else None,
    }
