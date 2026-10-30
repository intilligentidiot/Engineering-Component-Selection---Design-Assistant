"""Company login: off until APP_PASSWORD is set; then every page and API needs a valid session."""
from fastapi.testclient import TestClient

from app.main import app
from app import auth


def _client():
    auth._FAILS.clear()
    return TestClient(app)


def test_login_is_off_until_a_password_is_set(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    c = _client()
    assert c.get("/").status_code == 200
    assert c.get("/api/status").status_code == 200


def test_pages_and_api_need_a_session(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    c = _client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/api/status").status_code == 401
    assert c.get("/health").status_code == 200                 # Railway health check stays open
    assert c.get("/static/css/ui.css").status_code == 200       # login page styles
    assert c.get("/static/js/sizing.js", follow_redirects=False).status_code == 303


def test_right_password_signs_in_wrong_one_does_not(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    c = _client()
    bad = c.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert bad.status_code == 401 and "Wrong password" in bad.text
    ok = c.post("/login", data={"password": "s3cret-pass"}, follow_redirects=False)
    assert ok.status_code == 303 and auth.COOKIE in ok.cookies
    assert c.get("/api/status").status_code == 200
    assert "Sign out" in c.get("/").text
    c.get("/logout")
    assert c.get("/api/status").status_code == 401


def test_changing_the_password_signs_everyone_out(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "first")
    c = _client()
    c.post("/login", data={"password": "first"})
    assert c.get("/api/status").status_code == 200
    monkeypatch.setenv("APP_PASSWORD", "second")
    assert c.get("/api/status").status_code == 401


def test_forged_or_expired_cookie_is_refused(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    assert not auth.valid("9999999999.deadbeef")
    assert not auth.valid(auth._sign(1))                         # expired
    assert auth.valid(auth._sign(9_999_999_999))


def test_too_many_wrong_passwords_wait(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret-pass")
    c = _client()
    for _ in range(auth._MAX_FAILS):
        c.post("/login", data={"password": "x"})
    r = c.post("/login", data={"password": "s3cret-pass"}, follow_redirects=False)
    assert r.status_code == 429 and "Too many" in r.text
    auth._FAILS.clear()
