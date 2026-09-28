from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import gamification, models, services
from backend.database import get_db
from backend.deps import get_current_user, get_today
from backend.routers.auth import username_taken
from backend.schemas import ChangePasswordRequest, DeleteAccountRequest, ProfileUpdate
from backend.security import clear_session_cookie, create_access_token, hash_password, set_session_cookie, verify_password

router = APIRouter(prefix="/users", tags=["Users"])

LEADERBOARD_SIZE = 50


def stats(user: models.User, today: date) -> dict:
    daily_xp, daily_lessons = gamification.effective_daily(user, today)
    return {
        "username": user.username,
        "email": user.email,
        "avatar_url": services.avatar_url(user),
        "xp": user.xp,
        "streak": gamification.effective_streak(user, today),
        "last_lesson_date": user.last_lesson_date.isoformat() if user.last_lesson_date else None,
        "daily_xp": daily_xp,
        "daily_lessons": daily_lessons,
        "weekly_xp": user.weekly_xp,
        "league": gamification.normalize_league(user.league),
        "quests_completed": user.quests_completed,
        "month_quests": gamification.effective_month_quests(user, today),
        "has_password": user.hashed_password is not None,
        "goals": {
            "daily_xp": gamification.daily_goal(user),
            "daily_lessons": gamification.DAILY_LESSON_GOAL,
            "monthly_quests": gamification.MONTHLY_QUEST_GOAL,
        },
    }


@router.get("/me")
def get_user_stats(user: models.User = Depends(get_current_user), today: date = Depends(get_today)):
    # Read-only: daily/monthly counters roll over lazily when the next lesson is completed.
    return stats(user, today)


@router.patch("/me")
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if body.username is not None and body.username != user.username:
        if username_taken(db, body.username, exclude_id=user.id):
            raise HTTPException(status_code=400, detail="That username is already taken.")
        user.username = body.username
    if body.avatar is not None:
        if body.avatar.partition(":")[0] not in services.AVATAR_STYLES:
            raise HTTPException(status_code=422, detail="Pick one of the avatars shown.")
        user.avatar = body.avatar
    if body.daily_xp_goal is not None:
        if body.daily_xp_goal not in {goal for goal, _, _ in gamification.DAILY_GOAL_OPTIONS}:
            raise HTTPException(status_code=422, detail="Pick one of the daily goals shown.")
        user.daily_xp_goal = body.daily_xp_goal
    if body.onboarded is not None:
        user.onboarded = body.onboarded
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That username is already taken.")
    return {"username": user.username, "avatar_url": services.avatar_url(user), "daily_xp_goal": user.daily_xp_goal}


@router.post("/me/password")
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.hashed_password is not None and not verify_password(body.current_password or "", user.hashed_password):
        raise HTTPException(status_code=400, detail="Your current password is incorrect.")
    user.hashed_password = hash_password(body.new_password)
    user.token_version += 1  # other devices are signed out
    db.commit()
    set_session_cookie(response, create_access_token(user.id, user.token_version))
    return {"status": "ok", "message": "Password updated. Other devices were signed out."}


@router.post("/me/sign-out-everywhere")
def sign_out_everywhere(response: Response, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    user.token_version += 1
    db.commit()
    clear_session_cookie(response)
    return {"status": "ok"}


@router.delete("/me")
def delete_account(
    body: DeleteAccountRequest, response: Response, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)
):
    if body.confirm_username.strip().lower() != user.username.lower():
        raise HTTPException(status_code=400, detail="Type your username exactly to confirm.")
    db.delete(user)
    db.commit()
    clear_session_cookie(response)
    return {"status": "deleted"}


def _entry(user: models.User, rank: int, count: int, promote: int, demote: int, me_id: int, today: date) -> dict:
    return {
        "rank": rank,
        "username": user.username,
        "avatar_url": services.avatar_url(user, 64),
        "xp": user.weekly_xp,
        "streak": gamification.effective_streak(user, today),
        "zone": gamification.zone_for(rank, count, user.weekly_xp, promote, demote),
        "is_me": user.id == me_id,
    }


def leaderboard(db: Session, me: models.User, today: date) -> dict:
    """The weekly ranking of the current user's league."""
    league = gamification.normalize_league(me.league)
    in_league = db.query(models.User).filter(models.User.league == league)
    count = in_league.count()
    promote, demote = gamification.zone_sizes(league, count)

    top = in_league.order_by(models.User.weekly_xp.desc(), models.User.id).limit(LEADERBOARD_SIZE).all()
    entries = [_entry(u, i, count, promote, demote, me.id, today) for i, u in enumerate(top, start=1)]

    me_entry = next((e for e in entries if e["is_me"]), None)
    if me_entry is None:
        ahead = in_league.filter(
            or_(
                models.User.weekly_xp > me.weekly_xp,
                and_(models.User.weekly_xp == me.weekly_xp, models.User.id < me.id),
            )
        ).count()
        me_entry = _entry(me, ahead + 1, count, promote, demote, me.id, today)

    return {
        "league": league,
        "next_league": gamification.next_league(league),
        "previous_league": gamification.previous_league(league),
        "promote_count": promote,
        "demote_count": demote,
        "total": count,
        "entries": entries,
        "me": me_entry,
    }


@router.get("/leaderboard/data")
def get_leaderboard(
    db: Session = Depends(get_db),
    me: models.User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    return leaderboard(db, me, today)
