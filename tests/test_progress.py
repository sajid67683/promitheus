"""Streaks, daily/monthly quests, leagues and the weekly cron."""
from datetime import datetime, timezone

from backend import gamification, models
from backend.weekly_reset import process_weekly_shuffle
from tests.conftest import register, upload_txt
from tests.test_quiz import _finish_lesson


def _me(client, headers):
    return client.get("/users/me", headers=headers).json()


def test_streak_grows_on_consecutive_days_and_breaks_after_a_gap(client, clock):
    headers = register(client)
    upload_txt(client, headers)

    clock.set(2026, 9, 1, 12)
    _finish_lesson(client, headers, 0)
    assert _me(client, headers)["streak"] == 1

    # Visiting pages the next day must not break anything (this was the old bug).
    clock.set(2026, 9, 2, 9)
    _me(client, headers)
    _finish_lesson(client, headers, 1)
    assert _me(client, headers)["streak"] == 2

    _finish_lesson(client, headers, 2)  # second lesson the same day
    assert _me(client, headers)["streak"] == 2

    clock.set(2026, 9, 4, 9)  # skipped the 3rd
    assert _me(client, headers)["streak"] == 0
    _finish_lesson(client, headers, 3)
    me = _me(client, headers)
    assert me["streak"] == 1 and me["last_lesson_date"] == "2026-09-04"


def test_days_follow_the_users_timezone(client, clock):
    headers = register(client)
    upload_txt(client, headers)
    clock.set(2026, 9, 1, 20)  # 20:00 UTC = 02:00 next day in Dhaka
    _finish_lesson(client, {**headers, "X-Timezone": "Asia/Dhaka"}, 0)
    assert _me(client, {**headers, "X-Timezone": "Asia/Dhaka"})["last_lesson_date"] == "2026-09-02"
    # Garbage timezones fall back to UTC instead of erroring
    assert client.get("/users/me", headers={**headers, "X-Timezone": "../../etc/passwd"}).status_code == 200


def test_get_me_does_not_write(client, clock, db):
    headers = register(client)
    clock.set(2026, 9, 10, 12)
    _me(client, headers)
    user = db.query(models.User).one()
    assert user.stats_date is None


def test_daily_lessons_count_once_and_quests_are_real(client, clock):
    headers = register(client)
    upload_txt(client, headers)
    clock.set(2026, 9, 1, 12)

    _finish_lesson(client, headers, 0)  # 20 XP, 1 lesson -> lesson quest done
    me = _me(client, headers)
    assert me["daily_lessons"] == 1 and me["daily_xp"] == 20
    assert me["quests_completed"] == 1 and me["month_quests"] == 1

    _finish_lesson(client, headers, 3)  # +20 XP (40)
    _finish_lesson(client, headers, 1)  # +10 XP (50) -> XP quest done
    me = _me(client, headers)
    assert me["daily_lessons"] == 3 and me["daily_xp"] == 50
    assert me["quests_completed"] == 2

    clock.set(2026, 9, 2, 12)
    me = _me(client, headers)
    assert me["daily_xp"] == 0 and me["daily_lessons"] == 0 and me["month_quests"] == 2

    clock.set(2026, 10, 1, 12)
    assert _me(client, headers)["month_quests"] == 0


def test_zone_sizes():
    assert gamification.zone_sizes("Paper", 1) == (1, 0)
    assert gamification.zone_sizes("Paper", 30) == (10, 0)
    assert gamification.zone_sizes("Iron", 30) == (10, 10)
    assert gamification.zone_sizes("Iron", 90) == (10, 10)
    assert gamification.zone_sizes("Iron", 5) == (1, 1)
    assert gamification.zone_sizes("Diamond", 30) == (0, 10)
    # No XP this week, no promotion
    assert gamification.zone_for(1, 5, 0, 1, 1) == "safe"


def _make_users(db, league, xps):
    users = []
    for i, xp in enumerate(xps):
        u = models.User(username=f"{league.lower()}{i}", email=f"{league}{i}@x.com", league=league, weekly_xp=xp)
        db.add(u)
        users.append(u)
    db.commit()
    return users


def test_weekly_reset_promotes_demotes_and_runs_once_per_week(db):
    iron = _make_users(db, "Iron", [100, 90, 80, 70, 60, 0])  # 6 users: 2 promote, 2 demote
    paper = _make_users(db, "Paper", [0])  # alone with 0 XP: stays

    now = datetime(2026, 9, 28, 0, 5, tzinfo=timezone.utc)  # Monday just after midnight
    result = process_weekly_shuffle(db, now=now)
    assert result["status"] == "done" and result["week"] == "2026-W39"

    for u in iron + paper:
        db.refresh(u)
    assert [u.league for u in iron] == ["Bronze", "Bronze", "Iron", "Iron", "Paper", "Paper"]
    assert paper[0].league == "Paper"
    assert all(u.weekly_xp == 0 for u in iron)

    # A duplicate run (retry, second instance) is a no-op.
    assert process_weekly_shuffle(db, now=now)["status"] == "skipped"
    db.refresh(iron[0])
    assert iron[0].league == "Bronze"


def test_cron_endpoint_requires_the_secret(client):
    assert client.get("/api/cron/weekly-reset").status_code == 401
    assert client.get("/api/cron/weekly-reset", headers={"Authorization": "Bearer wrong"}).status_code == 401
    res = client.get("/api/cron/weekly-reset", headers={"Authorization": "Bearer test-cron-secret"})
    assert res.status_code == 200 and res.json()["status"] in ("done", "skipped")


def test_leaderboard_shows_only_my_league_with_server_zones(client, db):
    headers = register(client, "myself")
    db.query(models.User).filter_by(username="myself").update({"league": "Iron", "weekly_xp": 5})
    db.commit()
    _make_users(db, "Iron", [50, 40])
    _make_users(db, "Gold", [999])

    board = client.get("/users/leaderboard/data", headers=headers).json()
    assert board["league"] == "Iron" and board["next_league"] == "Bronze"
    assert board["total"] == 3 and board["promote_count"] == 1
    assert [e["username"] for e in board["entries"]] == ["iron0", "iron1", "myself"]
    assert board["entries"][0]["zone"] == "promote"
    assert board["me"]["is_me"] and board["me"]["rank"] == 3
