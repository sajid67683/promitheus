from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend import gamification, models
from backend.database import get_db
from backend.deps import get_current_user, get_today

router = APIRouter(prefix="/users", tags=["Users"])

LEADERBOARD_SIZE = 50


@router.get("/me")
def get_user_stats(user: models.User = Depends(get_current_user), today: date = Depends(get_today)):
    # Read-only: daily/monthly counters roll over lazily when the next lesson is completed.
    daily_xp, daily_lessons = gamification.effective_daily(user, today)
    return {
        "username": user.username,
        "email": user.email,
        "xp": user.xp,
        "streak": gamification.effective_streak(user, today),
        "last_lesson_date": user.last_lesson_date.isoformat() if user.last_lesson_date else None,
        "daily_xp": daily_xp,
        "daily_lessons": daily_lessons,
        "weekly_xp": user.weekly_xp,
        "league": gamification.normalize_league(user.league),
        "quests_completed": user.quests_completed,
        "month_quests": gamification.effective_month_quests(user, today),
        "goals": {
            "daily_xp": gamification.DAILY_XP_GOAL,
            "daily_lessons": gamification.DAILY_LESSON_GOAL,
            "monthly_quests": gamification.MONTHLY_QUEST_GOAL,
        },
    }


def _entry(user: models.User, rank: int, count: int, promote: int, demote: int, me_id: int, today: date) -> dict:
    return {
        "rank": rank,
        "username": user.username,
        "xp": user.weekly_xp,
        "streak": gamification.effective_streak(user, today),
        "zone": gamification.zone_for(rank, count, user.weekly_xp, promote, demote),
        "is_me": user.id == me_id,
    }


@router.get("/leaderboard/data")
def get_leaderboard(
    db: Session = Depends(get_db),
    me: models.User = Depends(get_current_user),
    today: date = Depends(get_today),
):
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
