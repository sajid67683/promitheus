"""Weekly league promotion/demotion.

Runs from Vercel Cron (GET /api/cron/weekly-reset, Mondays 00:00 UTC). Each ISO week is
processed at most once, so retries or duplicate invocations are harmless.

Run manually:  python -m backend.weekly_reset [--force]
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import gamification
from backend.models import LeagueReset, User

logger = logging.getLogger(__name__)


def week_key_for(now: datetime) -> str:
    """The ISO week that just ended (the cron fires right after Sunday)."""
    year, week, _ = (now - timedelta(days=1)).isocalendar()
    return f"{year}-W{week:02d}"


def process_weekly_shuffle(db: Session, now: datetime | None = None, force: bool = False) -> dict:
    now = now or gamification.now_utc()
    week_key = week_key_for(now)

    if not force:
        # Claim the week first. A concurrent second run blocks on this primary key and then fails.
        db.add(LeagueReset(week_key=week_key))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("League reset for %s already done; skipping", week_key)
            return {"status": "skipped", "week": week_key}

    # 1. Snapshot every user, grouped by their current league, before changing anything.
    users = db.query(User).order_by(User.weekly_xp.desc(), User.id).with_for_update().all()
    groups: dict[str, list[User]] = {league: [] for league in gamification.LEAGUE_ORDER}
    for user in users:
        groups[gamification.normalize_league(user.league)].append(user)

    # 2. Decide each user's new league from the snapshot.
    promoted = demoted = 0
    for league, members in groups.items():
        count = len(members)
        promote, demote = gamification.zone_sizes(league, count)
        for rank, user in enumerate(members, start=1):
            zone = gamification.zone_for(rank, count, user.weekly_xp, promote, demote)
            if zone == "promote":
                user.league = gamification.next_league(league)
                promoted += 1
            elif zone == "demote":
                user.league = gamification.previous_league(league)
                demoted += 1
            else:
                user.league = league
            user.weekly_xp = 0

    record = db.get(LeagueReset, week_key) or LeagueReset(week_key=week_key)
    record.promoted, record.demoted, record.ran_at = promoted, demoted, now
    db.merge(record)
    db.commit()
    logger.info("League reset %s: %d promoted, %d demoted", week_key, promoted, demoted)
    return {"status": "done", "week": week_key, "promoted": promoted, "demoted": demoted, "users": len(users)}


if __name__ == "__main__":
    import argparse

    from backend.database import SessionLocal

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run the weekly league reset now.")
    parser.add_argument("--force", action="store_true", help="run even if this week was already processed")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        print(process_weekly_shuffle(session, force=args.force))
    finally:
        session.close()
