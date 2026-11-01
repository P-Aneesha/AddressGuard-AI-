"""CSRF protection, password rules and password change."""
import pytest

from app import create_app

HEADER = {"X-Requested-With": "AddressGuard"}


@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'sec.db'}", "TESTING": True,
                      "CSRF_ENFORCE": True, "GROQ_API_KEY": "", "SECRET_KEY": "test"})
    yield app
    from models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_api_posts_without_the_app_header_are_blocked(app):
    client = app.test_client()
    blocked = client.post("/api/auth/register", json={"name": "A", "email": "a@x.local", "password": "pass12345"})
    assert blocked.status_code == 403 and blocked.get_json()["error_type"] == "CSRF"
    allowed = client.post("/api/auth/register", headers=HEADER,
                          json={"name": "A", "email": "a@x.local", "password": "pass12345"})
    assert allowed.status_code == 201
    assert client.get("/api/auth/me").status_code == 200  # reads need no header


def test_short_passwords_are_rejected(app):
    response = app.test_client().post("/api/auth/register", headers=HEADER,
                                      json={"name": "B", "email": "b@x.local", "password": "short"})
    assert response.status_code == 400 and "at least 8" in response.get_json()["error"]


def test_change_password(app):
    client = app.test_client()
    client.post("/api/auth/register", headers=HEADER, json={"name": "C", "email": "c@x.local", "password": "oldpass123"})
    wrong = client.post("/api/auth/change-password", headers=HEADER,
                        json={"current_password": "nope12345", "new_password": "newpass123"})
    assert wrong.status_code == 400
    ok = client.post("/api/auth/change-password", headers=HEADER,
                     json={"current_password": "oldpass123", "new_password": "newpass123"})
    assert ok.status_code == 200
    client.post("/api/auth/logout", headers=HEADER)
    assert client.post("/api/auth/login", headers=HEADER,
                       json={"email": "c@x.local", "password": "oldpass123"}).status_code == 401
    assert client.post("/api/auth/login", headers=HEADER,
                       json={"email": "c@x.local", "password": "newpass123"}).status_code == 200
