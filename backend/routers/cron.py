import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.weekly_reset import process_weekly_shuffle

router = APIRouter(prefix="/api/cron", tags=["Cron"], include_in_schema=False)


def _require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    # Vercel Cron sends "Authorization: Bearer $CRON_SECRET".
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured.")
    expected = f"Bearer {settings.cron_secret}"
    if not hmac.compare_digest((authorization or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/weekly-reset", dependencies=[Depends(_require_cron_secret)])
def weekly_reset(db: Session = Depends(get_db)):
    return process_weekly_shuffle(db)
