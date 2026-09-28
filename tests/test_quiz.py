import json

from backend import grading, models
from tests.conftest import FAKE_QUIZ, register, upload_txt

# Correct answers for the questions in FAKE_QUIZ that survive validation, keyed by prompt.
CORRECT = {
    q["prompt"]: q["answer"]
    for level in FAKE_QUIZ.values()
    if isinstance(level, list)
    for q in level
}


def _start(client, headers, lesson_index=0):
    lessons = client.get("/lessons/", headers=headers).json()
    res = client.post(f"/lessons/{lessons[lesson_index]['id']}/attempts", headers=headers)
    assert res.status_code == 200, res.text
    return lessons[lesson_index], res.json()


def _answer(q):
    correct = CORRECT[q["data"]["prompt"]]
    if isinstance(correct, str) and correct.lower() in ("true", "false"):
        return correct.capitalize()
    return correct


def _finish_lesson(client, headers, lesson_index=0, right=True):
    lesson, attempt = _start(client, headers, lesson_index)
    for q in attempt["questions"]:
        answer = _answer(q) if right else ("wrong" if q["type"] != "rearrange" else ["x"])
        res = client.post(
            f"/attempts/{attempt['attempt_id']}/answers",
            headers=headers,
            json={"question_id": q["question_id"], "answer": answer},
        )
        assert res.status_code == 200, res.text
    res = client.post(f"/attempts/{attempt['attempt_id']}/complete", headers=headers)
    assert res.status_code == 200, res.text
    return lesson, attempt, res.json()


def test_upload_builds_six_lessons_and_drops_malformed_questions(client):
    headers = register(client)
    res = upload_txt(client, headers)
    assert res.status_code == 200, res.text

    lessons = client.get("/lessons/", headers=headers).json()
    assert [l["title"] for l in lessons] == [
        "Free Recall", "Fill in the Blanks", "Multiple Choice", "True or False", "Rearrange Concepts", "Explain Concepts",
    ]
    assert lessons[0]["unit_title"] == "lecture"

    counts = [len(client.post(f"/lessons/{l['id']}/attempts", headers=headers).json()["questions"]) for l in lessons]
    assert counts == [2, 1, 1, 2, 1, 1]


def test_questions_sent_to_browser_never_contain_answers(client):
    headers = register(client)
    upload_txt(client, headers)
    for index in range(6):
        _, attempt = _start(client, headers, index)
        for q in attempt["questions"]:
            assert "answer" not in q["data"]
        if index != 4:  # rearrange chunks legitimately contain the answer pieces
            dumped = json.dumps(attempt)
            for q in attempt["questions"]:
                correct = CORRECT[q["data"]["prompt"]]
                if q["type"] in ("short_answer", "fill_blank", "explain"):
                    assert correct not in dumped


def test_xp_is_computed_by_the_server_and_only_once_per_lesson(client, clock):
    headers = register(client)
    upload_txt(client, headers)

    _, attempt, result = _finish_lesson(client, headers, lesson_index=0)
    assert result["xp_awarded"] == 2 * 10  # two correct answers
    assert client.get("/users/me", headers=headers).json()["xp"] == 20

    # Replaying the same lesson is practice: no more XP.
    _, _, replay = _finish_lesson(client, headers, lesson_index=0)
    assert replay["xp_awarded"] == 0
    assert client.get("/users/me", headers=headers).json()["xp"] == 20

    # Completing the same attempt again doesn't award anything new either.
    again = client.post(f"/attempts/{attempt['attempt_id']}/complete", headers=headers).json()
    assert again["xp_awarded"] == 20
    assert client.get("/users/me", headers=headers).json()["xp"] == 20


def test_wrong_answers_earn_nothing_and_reveal_the_solution(client, clock):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers, 2)  # multiple choice
    q = attempt["questions"][0]
    res = client.post(
        f"/attempts/{attempt['attempt_id']}/answers", headers=headers, json={"question_id": q["question_id"], "answer": "Melanin"}
    ).json()
    assert res == {"correct": False, "correct_answer": "Chlorophyll", "feedback": ""}
    done = client.post(f"/attempts/{attempt['attempt_id']}/complete", headers=headers).json()
    assert done["xp_awarded"] == 0


def test_old_client_trusting_endpoints_are_gone(client):
    headers = register(client)
    assert client.post("/users/update_xp", headers=headers, json={"xp": 999999}).status_code in (404, 405)
    assert client.post("/api/grade-answer", json={"question": "q", "student_answer": "a"}).status_code in (404, 405)


def test_cannot_finish_without_answering_everything(client):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers)
    res = client.post(f"/attempts/{attempt['attempt_id']}/complete", headers=headers)
    assert res.status_code == 400


def test_each_question_can_only_be_answered_once_per_attempt(client):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers)
    q = attempt["questions"][0]
    url = f"/attempts/{attempt['attempt_id']}/answers"
    assert client.post(url, headers=headers, json={"question_id": q["question_id"], "answer": "nope"}).status_code == 200
    assert client.post(url, headers=headers, json={"question_id": q["question_id"], "answer": _answer(q)}).status_code == 409


def test_answers_are_normalized(client):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers)
    q = next(q for q in attempt["questions"] if CORRECT[q["data"]["prompt"]] == "Chloroplast")
    res = client.post(
        f"/attempts/{attempt['attempt_id']}/answers",
        headers=headers,
        json={"question_id": q["question_id"], "answer": "  chloroplast. "},
    )
    assert res.json()["correct"] is True


def test_users_cannot_touch_each_others_lessons(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    upload_txt(client, alice)
    lesson, attempt = _start(client, alice)

    assert client.get("/lessons/", headers=bob).json() == []
    assert client.post(f"/lessons/{lesson['id']}/attempts", headers=bob).status_code == 404
    q = attempt["questions"][0]
    res = client.post(
        f"/attempts/{attempt['attempt_id']}/answers", headers=bob, json={"question_id": q["question_id"], "answer": "x"}
    )
    assert res.status_code == 404
    assert client.post(f"/attempts/{attempt['attempt_id']}/complete", headers=bob).status_code == 404


def test_explain_questions_are_graded_by_ai_with_a_daily_cap(client, fake_gemini, restore_settings):
    headers = register(client)
    upload_txt(client, headers)
    _, attempt = _start(client, headers, 5)
    q = attempt["questions"][0]
    url = f"/attempts/{attempt['attempt_id']}/answers"

    restore_settings.daily_ai_grading_limit = 0
    assert client.post(url, headers=headers, json={"question_id": q["question_id"], "answer": "Energy."}).status_code == 429

    restore_settings.daily_ai_grading_limit = 5
    res = client.post(url, headers=headers, json={"question_id": q["question_id"], "answer": "Energy."}).json()
    assert res["correct"] is True and res["feedback"] == "Nice explanation."


def test_upload_rejects_bad_files_with_4xx(client, restore_settings):
    headers = register(client)
    assert upload_txt(client, headers, name="notes.docx").status_code == 400
    assert upload_txt(client, headers, text="   ").status_code == 400
    bad_pdf = client.post(
        "/upload/lecture", headers=headers, files={"file": ("slides.pdf", b"not really a pdf", "application/pdf")}
    )
    assert bad_pdf.status_code == 400

    restore_settings.max_upload_bytes = 10
    assert upload_txt(client, headers, text="x" * 11).status_code == 413


def test_upload_accepts_uppercase_extension(client):
    headers = register(client)
    assert upload_txt(client, headers, name="C:\\fakepath\\LECTURE.TXT").status_code == 200
    assert client.get("/lessons/", headers=headers).json()[0]["unit_title"] == "LECTURE"


def test_upload_daily_limit(client, restore_settings):
    headers = register(client)
    restore_settings.daily_upload_limit = 1
    assert upload_txt(client, headers).status_code == 200
    assert upload_txt(client, headers).status_code == 429


def test_grading_helpers():
    q = models.Question(question_type="true_false", content={"answer": "True"})
    assert grading.grade_locally(q, "true")
    assert not grading.grade_locally(q, "")
    r = models.Question(question_type="rearrange", content={"answer": ["a", "b"]})
    assert grading.grade_locally(r, ["A", "b "])
    assert not grading.grade_locally(r, ["b", "a"])
    assert not grading.grade_locally(r, "a b")


def test_falls_back_to_another_model_when_gemini_is_overloaded(client, fake_gemini, monkeypatch, restore_settings):
    from google.genai import errors

    restore_settings.gemini_model = "busy-model"
    restore_settings.gemini_fallback_models = ["backup-model"]
    original = fake_gemini.models.generate_content
    used = []

    def flaky(model, contents, config):
        used.append(model)
        if model == "busy-model":
            raise errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
        return original(model=model, contents=contents, config=config)

    monkeypatch.setattr(fake_gemini.models, "generate_content", flaky)
    headers = register(client)
    assert upload_txt(client, headers).status_code == 200
    assert used == ["busy-model", "backup-model"]

    # When every model is down the user gets a clear 502, not a 500.
    restore_settings.gemini_fallback_models = []
    res = upload_txt(client, headers)
    assert res.status_code == 502 and "unavailable" in res.json()["detail"]
