import os
_TEST_DB = "/tmp/addressguard_test_auth.db"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)  # each fresh test run (or CI invocation) starts from a clean DB
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")
os.environ.setdefault("SECRET_KEY", "test")
os.environ["GROQ_API_KEY"] = ""

import pytest
from app import create_app
from models import db as _db

@pytest.fixture
def client(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/auth.db"
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_register_login_logout(client):
    r = client.post("/api/auth/register", json={"name": "Test User", "email": "u@test.com", "password": "secret123"})
    assert r.status_code == 201

    r = client.post("/api/auth/register", json={"name": "Test User", "email": "u@test.com", "password": "secret123"})
    assert r.status_code == 409  # duplicate email

    client.post("/api/auth/logout")
    r = client.get("/api/auth/me")
    assert r.get_json()["user"] is None

    r = client.post("/api/auth/login", json={"email": "u@test.com", "password": "wrongpass"})
    assert r.status_code == 401

    r = client.post("/api/auth/login", json={"email": "u@test.com", "password": "secret123"})
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "u@test.com"

def test_dashboard_requires_login(client):
    r = client.get("/dashboard")
    assert r.status_code == 302  # redirected to /login
