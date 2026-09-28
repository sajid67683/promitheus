import pytest

from tests.conftest import register, upload_txt

APP_PAGES = ["/dashboard", "/practice", "/library", "/leaderboard", "/quests", "/streaks", "/profile", "/settings", "/quiz/1"]


def test_landing_for_guests_and_redirect_for_members(client):
    res = client.get("/")
    assert res.status_code == 200 and "Turn your lecture notes into a daily practice habit" in res.text
    register(client)
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/dashboard"


@pytest.mark.parametrize("path", APP_PAGES)
def test_app_pages_require_login(client, path):
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/login?next=")


@pytest.mark.parametrize("path", APP_PAGES)
def test_app_pages_render_for_members(client, path):
    register(client)
    res = client.get(path)
    assert res.status_code == 200, path
    assert "/static/css/app.css" in res.text and "/static/js/app.js" in res.text


def test_new_users_are_sent_to_onboarding(client):
    register(client, onboarded=False)
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/welcome"
    assert client.get("/welcome").status_code == 200


def test_pages_show_only_the_signed_in_users_data(client):
    from fastapi.testclient import TestClient

    from backend.main import app

    register(client, "firstuser")
    with TestClient(app) as other:
        register(other, "seconduser")
        html = other.get("/dashboard").text
    assert "seconduser" in html and "firstuser" not in html


def test_dashboard_lists_units_and_escapes_titles(client, fake_gemini):
    from tests.conftest import FAKE_QUIZ

    headers = register(client)
    fake_gemini_quiz = dict(FAKE_QUIZ, lesson_title="<script>alert(1)</script>")
    import json
    from types import SimpleNamespace

    fake_gemini.models.generate_content = lambda model, contents, config: SimpleNamespace(text=json.dumps(fake_gemini_quiz))
    assert upload_txt(client, headers).status_code == 200
    html = client.get("/dashboard").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)</script>" not in html


def test_old_urls_redirect(client):
    for old, new in [("/users/leaderboard", "/leaderboard"), ("/users/profile", "/profile")]:
        res = client.get(old, follow_redirects=False)
        assert res.status_code == 301 and res.headers["location"] == new


def test_head_requests_work(client):
    assert client.head("/").status_code == 200
    assert client.head("/login").status_code == 200


def test_friendly_404_for_browsers_json_for_api(client):
    res = client.get("/no-such-page", headers={"Accept": "text/html"})
    assert res.status_code == 404 and "This page doesn't exist" in res.text
    res = client.get("/no-such-page", headers={"Accept": "application/json"})
    assert res.status_code == 404 and res.json() == {"detail": "Not Found"}


def test_google_button_only_when_configured(client, restore_settings):
    assert "accounts.google.com/gsi" not in client.get("/login").text
    restore_settings.google_client_id = "abc.apps.googleusercontent.com"
    html = client.get("/login").text
    assert "accounts.google.com/gsi" in html and 'data-client_id="abc.apps.googleusercontent.com"' in html


def test_forgot_password_link_only_when_email_configured(client, restore_settings):
    assert "Forgot password?" not in client.get("/login").text
    restore_settings.resend_api_key, restore_settings.email_from = "re_test", "Promitheus <hi@example.com>"
    assert "Forgot password?" in client.get("/login").text


def test_static_files_and_favicon(client):
    for path in ["/static/js/app.js", "/static/js/quiz.js", "/static/css/app.css", "/favicon.ico"]:
        assert client.get(path).status_code == 200, path


def test_active_nav_is_rendered_server_side(client):
    register(client)
    html = client.get("/quests").text
    assert 'href="/quests" class="nav-link" aria-current="page"' in html


def test_streak_calendar_month_navigation(client):
    register(client)
    assert client.get("/streaks?month=2026-01").status_code == 200
    assert client.get("/streaks?month=garbage").status_code == 200


def test_login_redirects_back_to_next(client):
    register(client)
    res = client.get("/login?next=/library", follow_redirects=False)
    assert res.headers["location"] == "/library"
    res = client.get("/login?next=//evil.example", follow_redirects=False)
    assert res.headers["location"] == "/dashboard"
