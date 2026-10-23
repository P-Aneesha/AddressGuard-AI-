"""Reliability tests for decision labels, PIN rules, persistence, exports and input handling."""
import csv
import io
import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

os.environ["GROQ_API_KEY"] = ""

import pytest

from services.decision_engine import make_decision
from services.decision_labels import (
    DECISIONS, LEGACY_DECISIONS, NEEDS_CONFIRMATION, VALIDATION_FAILED,
    VALIDATION_WARNING, VERIFIED, normalize_decision,
)
from services.pin_validator import validate_pin
from services.pipeline_orchestrator import run_pipeline
from services import report_service

CFG = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="test", GROQ_TIMEOUT_SECONDS=5)
VALID = "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210"


# ---------------------------------------------------------------- labels

def test_only_current_labels_are_produced():
    assert DECISIONS == [VERIFIED, NEEDS_CONFIRMATION, VALIDATION_WARNING, VALIDATION_FAILED]
    assert normalize_decision("FAKE ADDRESS") == VALIDATION_FAILED
    assert normalize_decision("SUSPICIOUS") == VALIDATION_WARNING
    assert normalize_decision("NEEDS VERIFICATION") == VALIDATION_WARNING
    assert normalize_decision(VERIFIED) == VERIFIED


@pytest.mark.parametrize("raw", [
    VALID,
    "asdfgh qwerty random address 000000 xyz",
    "Suresh Iyer, 14 Anna Salai, T Nagar, Chennai, Maharashtra, 600017, 9840012345",
    "Priya Reddy, Road No. 5, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
])
def test_every_decision_has_a_rule_and_reason(raw):
    r = run_pipeline(raw, CFG)
    assert r["decision"] in DECISIONS
    assert r["decision"] not in LEGACY_DECISIONS
    ex = r["explainability"]
    assert ex["decision_rule"] in {"D1", "D2", "D3", "D4", "D5", "D6"}
    assert ex["decision_explanation"][0].startswith(f"Rule {ex['decision_rule']}")
    assert ex["limitations"], "every result states what the checks cannot prove"


def test_identical_inputs_give_identical_results():
    raw = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655"
    first, second = run_pipeline(raw, CFG), run_pipeline(raw, CFG)
    for key in ("decision", "confidence", "risk_level", "corrections"):
        assert first[key] == second[key]


# ---------------------------------------------------------------- decision rules

def _geo(**overrides):
    geo = {"checks": {"city_state": "CONSISTENT", "pin_state": "CONSISTENT", "pin_city": "CONSISTENT",
                      "locality_city": "VERIFIED", "district_state": "INCOMPLETE"},
           "issues": [], "overall": "VERIFIED", "reference": {"india_post_rows": 1000}}
    geo.update(overrides)
    return geo


COMPLETE = {"name": "A", "phone": "9876543210", "house_number": "1", "street": "MG Road", "locality": "X",
            "city": "Hyderabad", "state": "Telangana", "pin_code": "500081"}
LOW = {"level": "LOW", "reasons": []}
NO_ANOMALY = {"severity": "NONE", "reasons": []}


def test_complete_consistent_address_is_verified():
    assert make_decision(COMPLETE, 100, LOW, _geo(), NO_ANOMALY, [])["decision"] == VERIFIED


def test_reference_unavailable_blocks_verified():
    result = make_decision(COMPLETE, 100, LOW, _geo(reference={"error": "FileNotFoundError"}), NO_ANOMALY, [])
    assert result["decision"] == NEEDS_CONFIRMATION
    assert any("Verification incomplete" in r for r in result["reasons"])


def test_unconfirmed_pin_blocks_verified():
    checks = dict(_geo()["checks"], pin_state="LIKELY_MATCH")
    result = make_decision(COMPLETE, 100, LOW, _geo(checks=checks, overall="LIKELY_MATCH"), NO_ANOMALY, [])
    assert result["decision"] == NEEDS_CONFIRMATION
    assert any("could not be confirmed" in r for r in result["reasons"])


def test_missing_fields_alone_never_produce_a_warning():
    sparse = {"city": "Hyderabad", "state": "Telangana"}
    high = {"level": "HIGH", "reasons": ["Invalid or missing phone number", "City missing"]}
    geo = _geo(checks={"city_state": "CONSISTENT"}, overall="VERIFIED")
    result = make_decision(sparse, 40, high, geo, NO_ANOMALY, [])
    assert result["decision"] == NEEDS_CONFIRMATION
    assert any("uncertainty, not proof" in r for r in result["reasons"])


def test_geographic_conflict_is_a_warning():
    checks = dict(_geo()["checks"], pin_state="INCONSISTENT")
    result = make_decision(COMPLETE, 50, {"level": "MEDIUM", "reasons": []},
                           _geo(checks=checks, issues=["PIN maps to Karnataka"], overall="INCONSISTENT"),
                           NO_ANOMALY, [])
    assert result["decision"] == VALIDATION_WARNING and result["rule"] == "D3"


def test_no_structure_is_validation_failed():
    result = make_decision({}, 0, {"level": "CRITICAL", "reasons": []}, _geo(),
                           {"severity": "CRITICAL", "reasons": ["No recognizable address components found"]}, [])
    assert result["decision"] == VALIDATION_FAILED and result["rule"] == "D1"


# ---------------------------------------------------------------- AI suggestion harmonisation

def test_ai_suggestions_use_reference_spelling_and_correct_field():
    from services.pipeline_orchestrator import _harmonize_ai_correction
    normalized = {"city": "Banglore", "state": "Karnatka", "district": ""}
    raw = "Sana Ali, Banglore, Karnatka, 560038"
    city = _harmonize_ai_correction({"field": "city", "original": "Banglore", "suggested": "Bangalore"}, normalized, raw)
    assert city["suggested"] == "Bengaluru"
    misfiled = _harmonize_ai_correction({"field": "district", "original": "Karnatka", "suggested": "Karnataka"}, normalized, raw)
    assert misfiled["field"] == "state"
    invented = _harmonize_ai_correction({"field": "locality", "original": "Jublee Hils", "suggested": "Jubilee Hills"}, normalized, raw)
    assert invented is None, "a suggestion for text that is not in the address is dropped"


def test_ai_results_are_cached_per_input():
    from utils.ai_cache import ResultCache
    cache = ResultCache(max_items=2)
    cache.put("a", {"x": [1]})
    got = cache.get("a")
    got["x"].append(2)
    assert cache.get("a") == {"x": [1]}, "cached values are isolated copies"
    cache.put("b", 1); cache.put("c", 2)
    assert cache.get("a") is None, "least recently used entry is evicted"


# ---------------------------------------------------------------- PIN rules

@pytest.mark.parametrize("pin, valid, error_type", [
    ("", False, "missing"),
    ("50008", False, "format"),
    ("5000811", False, "format"),
    ("012345", False, "format"),
    ("999999", False, "format"),
    ("500081", True, None),
])
def test_pin_format_rules(pin, valid, error_type):
    result = validate_pin(pin)
    assert result["valid"] is valid
    assert result["error_type"] == error_type


def test_known_pin_is_reference_confirmed():
    assert validate_pin("500081")["reference_found"] is True


def test_minor_spelling_error_does_not_raise_delivery_risk_above_low():
    raw = "Kavya Nair, Flat 806, Maple Crest Towers, 4th Main Road, Indranagar, Bengaluru, Karnataka, 560038, 9012345678"
    r = run_pipeline(raw, CFG)
    assert r["corrections"], "the typo should be suggested"
    assert r["risk_level"] == "LOW"


def test_geographic_conflict_caps_confidence():
    r = run_pipeline("Suresh Iyer, 14 Anna Salai, T Nagar, Chennai, Maharashtra, 600017, 9840012345", CFG)
    assert r["confidence"] <= 50
    assert any("capped at 50%" in line for line in r["explainability"]["confidence_explanation"])


# ---------------------------------------------------------------- reports

def _record(**overrides):
    record = {
        "validation_id": "ABC123DEF456", "created_at": "2026-10-22T10:00:00",
        "raw_address": 'Flat 3 & 4, "Lake <View>", =HYPERLINK("x"), Bengaluru',
        "decision": VALIDATION_WARNING, "decision_description": "desc", "risk_level": "HIGH", "confidence": 40,
        "parsed_data": {"name": "=cmd|' /C calc'!A0", "city": "Bengaluru", "_raw_correction_fields": {"x": "y"}},
        "corrections": [{"field": "city", "original": "Banglore", "suggested": "Bengaluru", "confidence": 95}],
        "explainability": {"geo_checks": {"pin_state": "CONSISTENT"}, "decision_explanation": ["Rule D3: conflict"],
                           "limitations": ["No guarantee of delivery"]},
    }
    record.update(overrides)
    return record


def test_pdf_handles_markup_characters():
    data = report_service.generate_pdf(_record()).getvalue()
    assert data.startswith(b"%PDF")


def test_csv_is_quoted_and_formula_safe():
    text = report_service.generate_csv(_record()).getvalue().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert ["Decision", VALIDATION_WARNING] in rows
    assert ["Raw Address", 'Flat 3 & 4, "Lake <View>", =HYPERLINK("x"), Bengaluru'] in rows
    name_row = next(r for r in rows if r and r[0] == "name")
    assert name_row[1].startswith("'="), "formula-like values are neutralised"
    assert not any(r and r[0].startswith("_") for r in rows), "internal fields are not exported"


def test_qr_and_barcode_encode_only_id_and_result():
    captured = {}
    with mock.patch.object(report_service.qrcode, "make", side_effect=lambda data: captured.setdefault("qr", data) and _Png()):
        report_service.generate_qr(_record())
    assert json.loads(captured["qr"]) == {"id": "ABC123DEF456", "decision": VALIDATION_WARNING, "confidence": 40}
    with mock.patch.object(report_service, "Code128") as code128:
        code128.return_value.write = lambda buf, options=None: None
        report_service.generate_barcode(_record())
    assert code128.call_args[0][0] == "ABC123DEF456"


class _Png:
    def save(self, buf, format=None):
        buf.write(b"png")


# ---------------------------------------------------------------- API, database and history

@pytest.fixture
def api(tmp_path):
    from evaluation.address_cases_30 import make_client
    return make_client(tmp_path / "reliability.db")


def test_duplicate_submission_returns_existing_record(api):
    app, client = api
    first = client.post("/api/validate", json={"raw_address": VALID})
    second = client.post("/api/validate", json={"raw_address": VALID})
    assert first.status_code == 201 and second.status_code == 200
    assert second.get_json()["duplicate"] is True
    assert second.get_json()["validation_id"] == first.get_json()["validation_id"]
    assert len(client.get("/api/history").get_json()["history"]) == 1


def test_legacy_records_are_migrated_and_counted(api):
    app, client = api
    from app import migrate_legacy_decisions
    from models import db
    from models.user import User
    from models.validation import Validation
    with app.app_context():
        uid = User.query.filter_by(email="cases@test.local").first().id
        for label in ("FAKE ADDRESS", "SUSPICIOUS", "NEEDS VERIFICATION"):
            db.session.add(Validation(user_id=uid, raw_address=f"old {label}", parsed_data={}, corrections=[],
                                      pipeline=[], explainability={}, decision=label,
                                      created_at=datetime.utcnow() - timedelta(days=30)))
        db.session.commit()
        old_id = Validation.query.filter_by(decision="FAKE ADDRESS").first().validation_id
        # Read-time mapping works even before the migration runs.
        assert client.get(f"/api/validation/{old_id}").get_json()["decision"] == VALIDATION_FAILED
        assert migrate_legacy_decisions() == 3
        assert migrate_legacy_decisions() == 0, "migration is idempotent"
        assert Validation.query.count() == 3, "no records were deleted"
    stats = client.get("/api/dashboard-stats").get_json()
    assert stats["decisions"][VALIDATION_FAILED] == 1
    assert stats["decisions"][VALIDATION_WARNING] == 2
    assert sum(stats["decisions"].values()) == stats["total_validations"]


def test_history_and_exports_work_for_a_stored_record(api):
    app, client = api
    created = client.post("/api/validate", json={"raw_address": VALID}).get_json()
    vid = created["validation_id"]
    history = client.get("/api/history").get_json()["history"]
    assert history[0]["validation_id"] == vid and history[0]["created_at"]
    for kind, mimetype in (("pdf", "application/pdf"), ("csv", "text/csv"), ("qr", "image/png"), ("barcode", "image/png")):
        response = client.get(f"/api/report/{vid}/{kind}")
        assert response.status_code == 200, kind
        assert response.mimetype == mimetype
    csv_text = client.get(f"/api/report/{vid}/csv").data.decode("utf-8-sig")
    assert f"Decision,{created['decision']}" in csv_text


def test_export_failure_returns_friendly_error(api):
    app, client = api
    vid = client.post("/api/validate", json={"raw_address": VALID}).get_json()["validation_id"]
    with mock.patch("routes.api.generate_pdf", side_effect=RuntimeError("boom")):
        response = client.get(f"/api/report/{vid}/pdf")
    assert response.status_code == 500
    assert response.get_json()["error_type"] == "TECHNICAL_FAILURE"
    assert "boom" not in response.get_data(as_text=True), "internal details are not exposed"


def test_revalidation_rejects_unknown_fields_and_empty_values(api):
    app, client = api
    vid = client.post("/api/validate", json={"raw_address": VALID}).get_json()["validation_id"]
    bad_field = client.post(f"/api/revalidate/{vid}", json={"accepted": [{"field": "user_id", "original": "1", "suggested": "2"}], "rejected": []})
    empty = client.post(f"/api/revalidate/{vid}", json={"accepted": [{"field": "city", "original": "a", "suggested": "  "}], "rejected": []})
    not_list = client.post(f"/api/revalidate/{vid}", json={"accepted": "city", "rejected": []})
    assert bad_field.status_code == empty.status_code == not_list.status_code == 400


def test_auth_endpoints_reject_malformed_bodies(api):
    app, client = api
    assert client.post("/api/auth/login", data="nonsense", content_type="text/plain").status_code == 401
    r = client.post("/api/auth/register", json={"name": ["x"], "email": 5, "password": None})
    assert r.status_code == 400 and r.is_json


def test_unknown_api_route_returns_json_404(api):
    app, client = api
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.is_json
