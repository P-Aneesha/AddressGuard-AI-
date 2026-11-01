"""Deleting a validation from History."""
import pytest

from app import create_app

TYPO = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655"


@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'del.db'}", "TESTING": True,
                      "GROQ_API_KEY": "", "SECRET_KEY": "test"})
    yield app
    from models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _user(app, email):
    client = app.test_client()
    client.post("/api/auth/register", json={"name": "U", "email": email, "password": "pass12345"})
    return client


def test_owner_can_delete_a_validation_and_its_review_decisions(app):
    from models.review_decision import ReviewDecision
    client = _user(app, "owner@test.local")
    created = client.post("/api/validate", json={"raw_address": TYPO}).get_json()
    vid = created["validation_id"]
    city = next(c for c in created["corrections"] if c["field"] == "city")
    client.post(f"/api/revalidate/{vid}", json={"accepted": [city], "rejected": []})
    with app.app_context():
        assert ReviewDecision.query.count() == 1

    response = client.delete(f"/api/validation/{vid}")
    assert response.status_code == 200 and response.get_json()["deleted"] == vid
    assert client.get(f"/api/validation/{vid}").status_code == 404
    assert client.get("/api/history").get_json()["history"] == []
    with app.app_context():
        assert ReviewDecision.query.count() == 0
    assert client.get("/api/dashboard-stats").get_json()["total_validations"] == 0


def test_another_users_validation_cannot_be_deleted(app):
    owner = _user(app, "a@test.local")
    vid = owner.post("/api/validate", json={"raw_address": TYPO}).get_json()["validation_id"]
    stranger = _user(app, "b@test.local")
    assert stranger.delete(f"/api/validation/{vid}").status_code == 404
    assert owner.get(f"/api/validation/{vid}").status_code == 200  # still there


def test_unknown_id_and_signed_out(app):
    client = _user(app, "c@test.local")
    assert client.delete("/api/validation/NOPE123").status_code == 404
    assert app.test_client().delete("/api/validation/NOPE123").status_code == 401
