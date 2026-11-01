"""Human accept/edit/reject decisions are recorded and give an acceptance rate."""
import pytest

from app import create_app

TYPO = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655"


@pytest.fixture
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'rev.db'}", "TESTING": True,
                      "GROQ_API_KEY": "", "SECRET_KEY": "test"})
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Rev", "email": "rev@test.local", "password": "pass12345"})
    yield c
    from models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_review_decisions_give_acceptance_rate(client):
    assert client.get("/api/dashboard-stats").get_json()["review"]["reviewed"] == 0

    result = client.post("/api/validate", json={"raw_address": TYPO}).get_json()
    by_field = {c["field"]: c for c in result["corrections"]}
    assert {"city", "state", "building"} <= set(by_field)

    edited = dict(by_field["building"], suggested="Green Heights Apts")  # reviewer changed the value
    response = client.post(f"/api/revalidate/{result['validation_id']}", json={
        "accepted": [by_field["city"], edited],
        "rejected": [by_field["state"]],
    })
    assert response.status_code == 200

    review = client.get("/api/dashboard-stats").get_json()["review"]
    assert (review["accepted"], review["edited"], review["rejected"]) == (1, 1, 1)
    assert review["acceptance_rate"] == pytest.approx(66.7)
    assert review["accepted_unchanged_rate"] == pytest.approx(33.3)
