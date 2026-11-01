"""Bulk CSV validation."""
import csv
import io

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'bulk.db'}", "TESTING": True,
                      "GROQ_API_KEY": "", "SECRET_KEY": "test"})
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Bulk", "email": "bulk@test.local", "password": "pass12345"})
    yield c
    from models import db
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _upload(client, text, name="orders.csv"):
    return client.post("/api/validate-bulk", data={"file": (io.BytesIO(text.encode("utf-8")), name)},
                       content_type="multipart/form-data")


def test_bulk_csv_is_validated_row_by_row(client):
    text = (
        "order_id,address\n"
        '1,"Ravi Kumar, 9876543210, Flat 302, Sai Residency, Hitech City Road, Madhapur, Hyderabad, Telangana 500081"\n'
        '2,"Ravi Kumar, 9876543210, Flat 302, Sai Residency, Hitech City Road, Madhapur, Hyderabad, Telangana 110001"\n'
        "3,lorem ipsum dolor sit amet\n"
        '4,"=HYPERLINK(""http://x"")"\n'
    )
    response = _upload(client, text)
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 4
    decisions = [r["decision"] for r in body["rows"]]
    assert decisions[0] == "VERIFIED"
    assert decisions[1] == "VALIDATION WARNING"
    assert decisions[2] == "VALIDATION FAILED"
    rows = list(csv.DictReader(io.StringIO(body["csv"])))
    assert len(rows) == 4 and rows[1]["suggested_corrections"].startswith("pin_code: 110001 -> 500081")
    assert rows[3]["raw_address"].startswith("'=")  # spreadsheet formula neutralised
    assert len(client.get("/api/history").get_json()["history"]) == 4  # every row is saved


def test_bulk_rejects_non_csv_and_too_many_rows(client):
    assert _upload(client, "address\nx", name="orders.xlsx").status_code == 400
    too_many = "address\n" + "\n".join(f"Flat {i}, Hyderabad, Telangana 500081" for i in range(51))
    response = _upload(client, too_many)
    assert response.status_code == 400 and "at most 50" in response.get_json()["error"]
