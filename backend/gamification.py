"""XP, streaks, daily/monthly quests and league rules, all in one place."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

XP_PER_CORRECT_ANSWER = 10
# Practice sessions pay less, and only the first time a past mistake is fixed.
XP_PER_FIXED_MISTAKE = 5
DAILY_XP_GOAL = 50  # default for new users
# (xp per day, label, description) offered during onboarding and in settings.
DAILY_GOAL_OPTIONS = [
    (20, "Casual", "About one lesson a day"),
    (50, "Regular", "Two or three lessons a day"),
    (100, "Serious", "Five lessons a day"),
    (200, "Intense", "A full study session every day"),
]
DAILY_LESSON_GOAL = 1
MONTHLY_QUEST_GOAL = 20

LEAGUE_ORDER = ["Paper", "Iron", "Bronze", "Silver", "Gold", "Platinum", "Diamond"]
MAX_PROMOTIONS = 10
MAX_DEMOTIONS = 10


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def valid_timezone(tz_name: str | None) -> bool:
    if not tz_name or len(tz_name) > 64:
        return False
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def user_today(tz_name: str | None) -> date:
    """Today's date in the user's timezone, falling back to UTC."""
    tz = ZoneInfo(tz_name) if valid_timezone(tz_name) else timezone.utc
    return now_utc().astimezone(tz).date()


def daily_goal(user) -> int:
    return user.daily_xp_goal or DAILY_XP_GOAL


def _month_key(day: date) -> str:
    return day.strftime("%Y-%m")


# ---------- read-only views (safe to use in GET requests) ----------

def effective_streak(user, today: date) -> int:
    """A streak only counts if the last lesson was today or yesterday."""
    if user.last_lesson_date and user.last_lesson_date >= today - timedelta(days=1):
        return user.streak or 0
    return 0


def effective_daily(user, today: date) -> tuple[int, int]:
    if user.stats_date == today:
        return user.daily_xp or 0, user.daily_lessons or 0
    return 0, 0


def effective_month_quests(user, today: date) -> int:
    return (user.month_quests or 0) if user.quest_month == _month_key(today) else 0


# ---------- writes ----------

def _roll_periods(user, today: date) -> None:
    if user.stats_date != today:
        user.daily_xp = 0
        user.daily_lessons = 0
        user.stats_date = today
    if user.quest_month != _month_key(today):
        user.month_quests = 0
        user.quest_month = _month_key(today)


def record_lesson_completion(user, today: date, xp: int) -> int:
    """Applies XP, streak and quest progress for one finished lesson.

    Returns how many daily quests were completed by this lesson.
    """
    _roll_periods(user, today)

    if user.last_lesson_date == today:
        pass  # already counted today
    elif user.last_lesson_date == today - timedelta(days=1):
        user.streak = (user.streak or 0) + 1
    else:
        user.streak = 1
    user.last_lesson_date = today

    xp_before, lessons_before = user.daily_xp, user.daily_lessons
    user.xp = (user.xp or 0) + xp
    user.weekly_xp = (user.weekly_xp or 0) + xp
    user.daily_xp = xp_before + xp
    user.daily_lessons = lessons_before + 1

    quests_done = 0
    if xp_before < daily_goal(user) <= user.daily_xp:
        quests_done += 1
    if lessons_before < DAILY_LESSON_GOAL <= user.daily_lessons:
        quests_done += 1
    user.quests_completed = (user.quests_completed or 0) + quests_done
    user.month_quests = (user.month_quests or 0) + quests_done
    return quests_done


# ---------- leagues ----------

def normalize_league(league: str | None) -> str:
    return league if league in LEAGUE_ORDER else LEAGUE_ORDER[0]


def next_league(league: str) -> str | None:
    idx = LEAGUE_ORDER.index(normalize_league(league))
    return LEAGUE_ORDER[idx + 1] if idx + 1 < len(LEAGUE_ORDER) else None


def previous_league(league: str) -> str | None:
    idx = LEAGUE_ORDER.index(normalize_league(league))
    return LEAGUE_ORDER[idx - 1] if idx > 0 else None


def zone_sizes(league: str, member_count: int) -> tuple[int, int]:
    """(promotion slots, demotion slots) for a league of this size.

    The top third (max 10) promote and the bottom third (max 10) demote, so a small
    league doesn't promote everyone every week.
    """
    promote = 0 if next_league(league) is None else min(MAX_PROMOTIONS, max(1, member_count // 3))
    demote = 0 if previous_league(league) is None else min(MAX_DEMOTIONS, member_count // 3)
    promote = min(promote, member_count)
    demote = min(demote, member_count - promote)
    return promote, demote


def zone_for(rank: int, member_count: int, weekly_xp: int, promote: int, demote: int) -> str:
    # You have to earn XP this week to be promoted.
    if rank <= promote and (weekly_xp or 0) > 0:
        return "promote"
    if rank > member_count - demote:
        return "demote"
    return "safe"
