import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Configure a throwaway SQLite database BEFORE the app is imported.
# (Existing environment variables win over .env, so the real .env is never used here.)
_TMP = Path(tempfile.mkdtemp(prefix="promitheus-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["CRON_SECRET"] = "test-cron-secret"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["ENVIRONMENT"] = "test"
os.environ.pop("VERCEL", None)
os.environ.pop("VERCEL_ENV", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend import ai_service, gamification  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend.main import app  # noqa: E402

FAKE_QUIZ = {
    "lesson_title": "Photosynthesis",
    "level_1_short_answer": [
        {"prompt": "What organelle performs photosynthesis?", "answer": "Chloroplast",
         "explanation": "Chloroplasts hold chlorophyll."},
        {"prompt": "What gas do plants release?", "answer": "Oxygen", "alternatives": ["O2"]},
    ],
    "level_2_fill_blank": [
        {"prompt": "Plants absorb ____ from the air.", "answer": "carbon dioxide"},
        {"prompt": "This one has no blank so it is dropped.", "answer": "x"},
    ],
    "level_3_mcq": [
        {"prompt": "Which pigment is green?", "options": ["Chlorophyll", "Carotene", "Xanthophyll", "Melanin"], "answer": "Chlorophyll"},
        {"prompt": "Answer not in options, dropped", "options": ["A", "B", "C", "D"], "answer": "E"},
    ],
    "level_4_true_false": [
        {"prompt": "Photosynthesis needs light.", "options": ["True", "False"], "answer": "true"},
        {"prompt": "Roots perform photosynthesis.", "options": ["True", "False"], "answer": "False"},
    ],
    "level_5_rearrange": [
        {"prompt": "Order the steps:", "chunks": ["absorb light", "split water", "make sugar"], "answer": ["absorb light", "split water", "make sugar"]},
        {"prompt": "Not a permutation, dropped", "chunks": ["a", "b"], "answer": ["a", "c"]},
    ],
    "level_6_explain": [
        {"prompt": "Explain why plants need light.", "answer": "Light provides the energy to make sugar."},
    ],
}


class FakeGemini:
    """Stands in for google.genai.Client; returns canned JSON."""

    def __init__(self):
        self.grade = {"is_correct": True, "feedback": "Nice explanation."}
        self.equivalent = False
        self.calls = 0
        self.models_used = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, config):
        self.calls += 1
        self.models_used.append(model)
        instructions = config.system_instruction or ""
        if "short quiz answer" in instructions:
            return SimpleNamespace(text=json.dumps({"equivalent": self.equivalent}))
        if instructions:  # explanation grading
            return SimpleNamespace(text=json.dumps(self.grade))
        return SimpleNamespace(text=json.dumps(FAKE_QUIZ))


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def fake_gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(ai_service, "_get_client", lambda: fake)
    return fake


class Clock:
    def __init__(self, monkeypatch):
        self.now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(gamification, "now_utc", lambda: self.now)

    def set(self, *args):
        self.now = datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def restore_settings():
    saved = dict(vars(settings))
    yield settings
    vars(settings).clear()
    vars(settings).update(saved)


def register(client, username="alice", email=None, password="correct horse battery", onboarded=True):
    """Creates a user. Returns Bearer headers (the client's cookie jar is also logged in)."""
    res = client.post(
        "/auth/register",
        json={"username": username, "email": email or f"{username}@example.com", "password": password},
    )
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    if onboarded:
        assert client.patch("/users/me", headers=headers, json={"onboarded": True}).status_code == 200
    return headers


def upload_txt(client, headers, name="lecture.txt", text="Plants use light to make sugar."):
    return client.post("/upload/lecture", headers=headers, files={"file": (name, text.encode(), "text/plain")})
