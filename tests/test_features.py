"""Sessions, password reset, grading improvements, reports, practice, library and settings."""
from datetime import timedelta

from fastapi.testclient import TestClient

from backend import gamification, mailer, models
from backend.config import settings
from backend.main import app
from tests.conftest import register, upload_txt
from tests.test_quiz import _answer, _finish_lesson, _start


# ---------- sessions & security ----------

def test_login_sets_httponly_session_cookie_and_logout_clears_it(client):
    res = client.post("/auth/register", json={"username": "cookie", "email": "c@example.com", "password": "longenough"})
    cookie = res.headers["set-cookie"]
    assert settings.session_cookie in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert client.get("/users/me").status_code == 200  # cookie alone authenticates
    client.post("/auth/logout")
    assert client.get("/users/me").status_code == 401


def test_cross_site_posts_are_blocked(client):
    headers = register(client)
    res = client.post("/upload/sample", headers={**headers, "Origin": "https://evil.example"})
    assert res.status_code == 403
    res = client.post("/auth/login", json={"username": "x", "password": "y"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_password_change_signs_out_other_sessions(client):
    old = register(client, "pat")
    with TestClient(app) as phone:
        phone.post("/auth/login", json={"username": "pat", "password": "correct horse battery"})
        assert phone.get("/users/me").status_code == 200

        bad = client.post("/users/me/password", headers=old, json={"current_password": "nope", "new_password": "brand-new-pw"})
        assert bad.status_code == 400
        ok = client.post("/users/me/password", headers=old, json={"current_password": "correct horse battery", "new_password": "brand-new-pw"})
        assert ok.status_code == 200

        assert phone.get("/users/me").status_code == 401  # other device signed out
        assert client.get("/users/me", headers=old).status_code == 401  # old token dead
        assert client.get("/users/me").status_code == 200  # this browser got a fresh cookie
    assert client.post("/auth/login", json={"username": "pat", "password": "brand-new-pw"}).status_code == 200


def test_sign_out_everywhere(client):
    headers = register(client)
    assert client.post("/users/me/sign-out-everywhere", headers=headers).status_code == 200
    assert client.get("/users/me", headers=headers).status_code == 401


def test_password_reset_flow(client, monkeypatch, clock):
    register(client, "rita", email="rita@example.com")
    sent = []
    monkeypatch.setattr(mailer, "send_password_reset", lambda to, username, link: sent.append(link))

    # Same answer for unknown emails (no account discovery)
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    known = client.post("/auth/forgot-password", json={"email": "RITA@example.com"})
    assert unknown.json() == known.json() and len(sent) == 1
    token = sent[0].split("token=")[1]

    assert client.post("/auth/reset-password", json={"token": "wrong", "password": "another-pass"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": token, "password": "another-pass"}).status_code == 200
    assert client.post("/auth/login", json={"username": "rita", "password": "another-pass"}).status_code == 200
    # single use
    assert client.post("/auth/reset-password", json={"token": token, "password": "third-pass-1"}).status_code == 400


def test_password_reset_links_expire(client, monkeypatch, clock):
    register(client, "eddie", email="ed@example.com")
    sent = []
    monkeypatch.setattr(mailer, "send_password_reset", lambda to, username, link: sent.append(link))
    client.post("/auth/forgot-password", json={"email": "ed@example.com"})
    clock.now = clock.now + timedelta(hours=2)
    token = sent[0].split("token=")[1]
    assert client.post("/auth/reset-password", json={"token": token, "password": "another-pass"}).status_code == 400


# ---------- grading ----------

def _answer_first(client, headers, lesson_index, pick, answer):
    _, attempt = _start(client, headers, lesson_index)
    q = next(q for q in attempt["questions"] if pick(q))
    res = client.post(
        f"/attempts/{attempt['attempt_id']}/answers", headers=headers, json={"question_id": q["question_id"], "answer": answer}
    )
    return attempt, q, res.json()


def test_small_typos_count_as_correct_and_are_flagged(client):
    headers = register(client)
    upload_txt(client, headers)
    _, _, res = _answer_first(client, headers, 0, lambda q: "organelle" in q["data"]["prompt"], "chloroplsat")
    assert res["correct"] is True and res["typo"] is True and res["correct_answer"] == "Chloroplast"
    assert res["explanation"] == "Chloroplasts hold chlorophyll."


def test_alternative_answers_are_accepted(client):
    headers = register(client)
    upload_txt(client, headers)
    _, _, res = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "O2")
    assert res["correct"] is True and res["typo"] is False


def test_ai_double_checks_free_recall_answers(client, fake_gemini):
    headers = register(client)
    upload_txt(client, headers)
    fake_gemini.equivalent = True
    _, _, res = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "the gas we breathe in")
    assert res["correct"] is True
    fake_gemini.equivalent = False
    _, _, res = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "nitrogen")
    assert res["correct"] is False


def test_ai_double_check_failure_falls_back_to_wrong(client, fake_gemini, monkeypatch):
    from backend import ai_service

    headers = register(client)
    upload_txt(client, headers)

    def boom(*args, **kwargs):
        raise ai_service.AIServiceError("down")

    monkeypatch.setattr(ai_service, "check_equivalent", boom)
    _, _, res = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "nitrogen")
    assert res["correct"] is False


# ---------- results, reports, practice ----------

def test_results_include_a_mistakes_review_and_next_lesson(client):
    headers = register(client)
    upload_txt(client, headers)
    lesson, _, result = _finish_lesson(client, headers, 0, right=False)
    assert result["correct"] == 0 and len(result["mistakes"]) == 2
    mistake = result["mistakes"][0]
    assert {"prompt", "your_answer", "correct_answer", "explanation"} <= mistake.keys()
    assert mistake["your_answer"] == "wrong"
    assert result["next_lesson_id"] == client.get("/lessons/", headers=headers).json()[1]["id"]


def test_accept_my_answer_clears_the_mistake_without_xp(client):
    headers = register(client)
    upload_txt(client, headers)
    attempt, q, res = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "Oxygen gas molecules")
    assert res["correct"] is False
    report = client.post(
        f"/questions/{q['question_id']}/report", headers=headers,
        json={"reason": "accept_my_answer", "attempt_id": attempt["attempt_id"]},
    )
    assert report.json()["accepted"] is True
    assert "gas" not in client.get("/practice", headers=headers).text.split("Your mistakes")[-1]

    # Accepted next time
    _, _, again = _answer_first(client, headers, 0, lambda q: "gas" in q["data"]["prompt"], "oxygen gas molecules")
    assert again["correct"] is True


def test_reporting_a_bad_question_hides_it(client):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers, 0)
    qid = attempt["questions"][0]["question_id"]
    assert client.post(f"/questions/{qid}/report", headers=headers, json={"reason": "wrong_or_unclear"}).json()["hidden"]
    _, again = _start(client, headers, 0)
    assert qid not in [q["question_id"] for q in again["questions"]]


def test_reports_are_owner_only(client):
    alice = register(client, "alice")
    upload_txt(client, alice)
    _, attempt = _start(client, alice, 0)
    with TestClient(app) as other:
        bob = register(other, "bob")
        res = other.post(f"/questions/{attempt['questions'][0]['question_id']}/report", headers=bob, json={"reason": "other"})
        assert res.status_code == 404


def test_practice_uses_open_mistakes_and_pays_once(client, clock):
    headers = register(client)
    upload_txt(client, headers)
    assert client.post("/practice/attempts", headers=headers).status_code == 404  # nothing yet

    _finish_lesson(client, headers, 0, right=False)  # 2 mistakes
    xp_before = client.get("/users/me", headers=headers).json()["xp"]

    practice = client.post("/practice/attempts", headers=headers).json()
    assert practice["kind"] == "practice" and len(practice["questions"]) == 2
    for q in practice["questions"]:
        client.post(f"/attempts/{practice['attempt_id']}/answers", headers=headers,
                    json={"question_id": q["question_id"], "answer": _answer(q)})
    done = client.post(f"/attempts/{practice['attempt_id']}/complete", headers=headers).json()
    assert done["xp_awarded"] == 2 * gamification.XP_PER_FIXED_MISTAKE
    assert client.get("/users/me", headers=headers).json()["xp"] == xp_before + 10
    assert client.post("/practice/attempts", headers=headers).status_code == 404  # all fixed

    # Getting them wrong again and re-fixing doesn't pay twice.
    _finish_lesson(client, headers, 0, right=False)
    practice = client.post("/practice/attempts", headers=headers).json()
    for q in practice["questions"]:
        client.post(f"/attempts/{practice['attempt_id']}/answers", headers=headers,
                    json={"question_id": q["question_id"], "answer": _answer(q)})
    assert client.post(f"/attempts/{practice['attempt_id']}/complete", headers=headers).json()["xp_awarded"] == 0


# ---------- library ----------

def _material_id(client, headers):
    return client.get("/lessons/", headers=headers).json()[0]["material_id"]


def test_rename_and_delete_unit_keeps_history(client, db, clock):
    headers = register(client)
    upload_txt(client, headers)
    _finish_lesson(client, headers, 0)
    mid = _material_id(client, headers)

    assert client.patch(f"/materials/{mid}", headers=headers, json={"title": "  Bio   101 "}).json()["title"] == "Bio 101"
    assert client.patch(f"/materials/{mid}", headers=headers, json={"title": "   "}).status_code == 422

    xp = client.get("/users/me", headers=headers).json()["xp"]
    assert client.delete(f"/materials/{mid}", headers=headers).status_code == 200
    assert client.get("/lessons/", headers=headers).json() == []
    assert client.get("/users/me", headers=headers).json()["xp"] == xp
    attempt = db.query(models.LessonAttempt).one()
    assert attempt.lesson_id is None and attempt.completed_on is not None  # activity calendar survives


def test_regenerate_replaces_questions_and_counts_toward_limit(client, restore_settings):
    headers = register(client)
    upload_txt(client, headers)
    mid = _material_id(client, headers)
    _finish_lesson(client, headers, 0)
    res = client.post(f"/materials/{mid}/regenerate", headers=headers)
    assert res.status_code == 200, res.text
    lessons = client.get("/lessons/", headers=headers).json()
    assert len(lessons) == 6
    assert not any(l["is_completed"] for l in lessons)  # progress starts over

    restore_settings.daily_upload_limit = 2
    assert client.post(f"/materials/{mid}/regenerate", headers=headers).status_code == 429


def test_deleting_and_reuploading_does_not_reset_the_daily_limit(client, restore_settings):
    headers = register(client)
    restore_settings.daily_upload_limit = 1
    assert upload_txt(client, headers).status_code == 200
    client.delete(f"/materials/{_material_id(client, headers)}", headers=headers)
    assert upload_txt(client, headers).status_code == 429


def test_library_is_owner_only(client):
    alice = register(client, "alice")
    upload_txt(client, alice)
    mid = _material_id(client, alice)
    with TestClient(app) as other:
        bob = register(other, "bob")
        assert other.patch(f"/materials/{mid}", headers=bob, json={"title": "mine"}).status_code == 404
        assert other.delete(f"/materials/{mid}", headers=bob).status_code == 404
        assert other.post(f"/materials/{mid}/regenerate", headers=bob).status_code == 404


def test_sample_lecture_for_onboarding(client):
    headers = register(client, onboarded=False)
    res = client.post("/upload/sample", headers=headers)
    assert res.status_code == 200 and res.json()["first_lesson_id"]


# ---------- settings ----------

def test_profile_updates_are_validated(client):
    headers = register(client, "sam")
    with TestClient(app) as other:
        register(other, "taken")
    assert client.patch("/users/me", headers=headers, json={"username": "TAKEN"}).status_code == 400
    assert client.patch("/users/me", headers=headers, json={"username": "<b>x</b>"}).status_code == 422
    assert client.patch("/users/me", headers=headers, json={"username": "samuel"}).json()["username"] == "samuel"
    assert client.patch("/users/me", headers=headers, json={"avatar": "evil:x"}).status_code == 422
    assert client.patch("/users/me", headers=headers, json={"avatar": "bottts:x y"}).status_code == 422
    assert "adventurer" in client.patch("/users/me", headers=headers, json={"avatar": "adventurer:ember"}).json()["avatar_url"]
    assert client.patch("/users/me", headers=headers, json={"daily_xp_goal": 37}).status_code == 422
    assert client.patch("/users/me", headers=headers, json={"daily_xp_goal": 100}).json()["daily_xp_goal"] == 100
    assert client.get("/users/me", headers=headers).json()["goals"]["daily_xp"] == 100


def test_daily_goal_changes_the_xp_quest(client, clock):
    headers = register(client)
    client.patch("/users/me", headers=headers, json={"daily_xp_goal": 20})
    upload_txt(client, headers)
    _finish_lesson(client, headers, 0)  # 20 XP
    assert client.get("/users/me", headers=headers).json()["quests_completed"] == 2


def test_google_users_can_set_a_password(client, db):
    headers = register(client, "gina")
    db.query(models.User).filter_by(username="gina").update({"hashed_password": None})
    db.commit()
    assert client.post("/users/me/password", headers=headers, json={"new_password": "now-i-have-one"}).status_code == 200
    assert client.post("/auth/login", json={"username": "gina", "password": "now-i-have-one"}).status_code == 200


def test_delete_account_needs_confirmation_and_removes_everything(client, db):
    headers = register(client, "dora")
    upload_txt(client, headers)
    assert client.request("DELETE", "/users/me", headers=headers, json={"confirm_username": "nope"}).status_code == 400
    assert client.request("DELETE", "/users/me", headers=headers, json={"confirm_username": "DORA"}).status_code == 200
    assert db.query(models.User).count() == 0
    assert db.query(models.SourceMaterial).count() == 0
    assert client.get("/users/me", headers=headers).status_code == 401
