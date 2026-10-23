"""Serverless deployment behaviour: rate limits, packaged index, hosting checks."""
import os
from unittest import mock

import pytest

from app import _configure_hosting, create_app
from services import official_reference_service as ref

ADDRESS = "Ravi Kumar, 9876543210, Flat 302, Sai Residency, Hitech City Road, Madhapur, Hyderabad, Telangana 500081"


@pytest.fixture
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'rl.db'}", "TESTING": True,
                      "GROQ_API_KEY": "", "SECRET_KEY": "test"})
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "RL", "email": "rl@test.local", "password": "pass12345"})
    yield c
    from models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_validation_is_rate_limited(client):
    with mock.patch.dict(os.environ, {"RATELIMIT_ENABLED": "1", "RATELIMIT_VALIDATE": "2/60"}):
        codes = [client.post("/api/validate", json={"raw_address": ADDRESS}).status_code for _ in range(3)]
        blocked = client.post("/api/validate", json={"raw_address": ADDRESS})
    assert all(c in (200, 201) for c in codes[:2])
    assert codes[2] == 429
    assert blocked.get_json()["error_type"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) > 0


def test_failed_logins_are_rate_limited(client):
    with mock.patch.dict(os.environ, {"RATELIMIT_ENABLED": "1", "RATELIMIT_LOGIN": "2/300"}):
        codes = [client.post("/api/auth/login", json={"email": "rl@test.local", "password": "wrong"}).status_code
                 for _ in range(3)]
    assert codes == [401, 401, 429]


def test_rate_limits_are_off_in_tests_by_default(client):
    with mock.patch.dict(os.environ, {"RATELIMIT_VALIDATE": "1/60"}):
        os.environ.pop("RATELIMIT_ENABLED", None)
        codes = [client.post("/api/validate", json={"raw_address": ADDRESS}).status_code for _ in range(3)]
    assert 429 not in codes


@pytest.mark.skipif(not ref.PACKAGED_INDEX.exists(), reason="run scripts/package_reference_index.py first")
def test_packaged_index_is_used_without_csvs(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIA_POST_PINCODE_CSV", str(tmp_path / "missing.csv"))
    monkeypatch.setenv("POSTAL_LGD_MAPPING_CSV", str(tmp_path / "missing2.csv"))
    monkeypatch.setenv("REFERENCE_INDEX_DB", str(tmp_path / "missing.sqlite3"))
    monkeypatch.setenv("REFERENCE_INDEX_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(ref, "_PACKAGED_DB", None)
    db = ref._ensure_index()
    assert db.parent == tmp_path and ref._index_compatible(db)


@pytest.mark.parametrize("secret", ["change-this", "short"])
def test_vercel_refuses_weak_secret_key(secret):
    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = secret
    with mock.patch.dict(os.environ, {"VERCEL": "1"}), pytest.raises(RuntimeError, match="SECRET_KEY"):
        _configure_hosting(app)


def test_vercel_enables_secure_cookies():
    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x" * 64
    with mock.patch.dict(os.environ, {"VERCEL": "1"}):
        _configure_hosting(app)
    assert app.config["SESSION_COOKIE_SECURE"] is True
