import logging
from datetime import datetime, timedelta, timezone

import jwt

from backend.routers import auth as auth_router
from tests.conftest import register


def test_register_returns_token_and_login_by_username_or_email(client):
    headers = register(client, "Alice")
    assert client.get("/users/me", headers=headers).json()["username"] == "Alice"

    for identifier in ("alice", "ALICE@example.com"):
        res = client.post("/auth/login", json={"username": identifier, "password": "correct horse battery"})
        assert res.status_code == 200, identifier
        assert res.json()["username"] == "Alice"


def test_register_rejects_html_in_username(client):
    res = client.post(
        "/auth/register",
        json={"username": "<img src=x onerror=alert(1)>", "email": "x@example.com", "password": "longenough"},
    )
    assert res.status_code == 422


def test_register_rejects_duplicates_case_insensitively(client):
    register(client, "Alice")
    res = client.post("/auth/register", json={"username": "aLiCe", "email": "other@example.com", "password": "longenough"})
    assert res.status_code == 400
    res = client.post("/auth/register", json={"username": "bob", "email": "ALICE@example.com", "password": "longenough"})
    assert res.status_code == 400


def test_register_validates_password_and_email(client):
    base = {"username": "bob", "email": "bob@example.com", "password": "longenough"}
    assert client.post("/auth/register", json={**base, "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={**base, "password": "é" * 40}).status_code == 422  # 80 bytes
    assert client.post("/auth/register", json={**base, "email": "not-an-email"}).status_code == 422


def test_password_is_never_logged(client, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        register(client, "carol", password="SuperSecret-Password-42")
    captured = capsys.readouterr()
    assert "SuperSecret-Password-42" not in caplog.text + captured.out + captured.err


def test_wrong_password_and_unknown_user_get_same_error(client):
    register(client, "dave")
    wrong = client.post("/auth/login", json={"username": "dave", "password": "wrong password"})
    unknown = client.post("/auth/login", json={"username": "nobody", "password": "wrong password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_tokens_signed_with_the_old_hardcoded_key_are_rejected(client):
    register(client, "erin")
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    for sub in ("1", "erin"):
        forged = jwt.encode({"sub": sub, "exp": exp}, "Promitheus_development_key_1716493987", algorithm="HS256")
        assert client.get("/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_protected_endpoints_require_a_token(client):
    for method, path in [
        ("get", "/users/me"),
        ("get", "/lessons/"),
        ("get", "/users/leaderboard/data"),
        ("post", "/lessons/1/attempts"),
        ("post", "/upload/lecture"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path


def test_google_login_disabled_without_client_id(client):
    assert client.post("/auth/google", json={"credential": "x"}).status_code == 503


def _fake_google(monkeypatch, restore_settings, **claims):
    restore_settings.google_client_id = "test-client-id"
    info = {"sub": "google-123", "email": "Jane@Gmail.com", "email_verified": True, "name": "Jane Doe"}
    info.update(claims)
    monkeypatch.setattr(auth_router.id_token, "verify_oauth2_token", lambda token, request, audience: info)


def test_google_login_creates_account_with_safe_username(client, monkeypatch, restore_settings):
    _fake_google(monkeypatch, restore_settings, name="Jane <script>Doe</script>")
    res = client.post("/auth/google", json={"credential": "token"})
    assert res.status_code == 200
    username = res.json()["username"]
    assert "<" not in username and ">" not in username

    # Signing in again finds the same account
    again = client.post("/auth/google", json={"credential": "token"})
    assert again.json()["username"] == username


def test_google_login_same_display_name_gets_unique_username(client, monkeypatch, restore_settings):
    _fake_google(monkeypatch, restore_settings)
    first = client.post("/auth/google", json={"credential": "t"}).json()["username"]
    _fake_google(monkeypatch, restore_settings, sub="google-456", email="other@gmail.com")
    second = client.post("/auth/google", json={"credential": "t"})
    assert second.status_code == 200
    assert second.json()["username"] != first


def test_google_login_does_not_hijack_existing_password_account(client, monkeypatch, restore_settings):
    # Attacker registers with the victim's email (and a username equal to it would be rejected anyway).
    register(client, "attacker", email="jane@gmail.com")
    _fake_google(monkeypatch, restore_settings)
    assert client.post("/auth/google", json={"credential": "t"}).status_code == 409


def test_google_login_requires_verified_email(client, monkeypatch, restore_settings):
    _fake_google(monkeypatch, restore_settings, email_verified=False)
    assert client.post("/auth/google", json={"credential": "t"}).status_code == 401
