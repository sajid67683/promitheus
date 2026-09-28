import pytest


@pytest.mark.parametrize(
    "path", ["/", "/dashboard", "/quiz/1", "/quests", "/streaks", "/leaderboard", "/profile", "/login"]
)
def test_pages_render(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert "<html" in res.text
    assert "/static/js/scripts.js" in res.text


def test_pages_do_not_leak_another_users_data(client):
    from tests.conftest import register

    register(client, "firstuser")
    assert "firstuser" not in client.get("/").text


def test_old_urls_redirect(client):
    for old, new in [("/users/leaderboard", "/leaderboard"), ("/users/profile", "/profile")]:
        res = client.get(old, follow_redirects=False)
        assert res.status_code == 301 and res.headers["location"] == new


def test_google_button_only_when_configured(client, restore_settings):
    assert "accounts.google.com/gsi" not in client.get("/login").text
    restore_settings.google_client_id = "abc.apps.googleusercontent.com"
    html = client.get("/login").text
    assert "accounts.google.com/gsi" in html and 'data-client_id="abc.apps.googleusercontent.com"' in html


def test_static_files_and_favicon(client):
    assert client.get("/static/js/scripts.js").status_code == 200
    assert client.get("/static/audio/wrong.mp3").status_code == 200
    assert client.get("/favicon.ico").status_code == 200


def test_active_nav_is_rendered_server_side(client):
    html = client.get("/quests").text
    assert 'id="nav-quests" class="nav-item active"' in html
