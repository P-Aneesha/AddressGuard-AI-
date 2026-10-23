"""The 30-case address test suite and the harness that executes it.

Each case is sent through the real Flask API (test client, temporary SQLite
database) exactly as the dashboard would send it. Fault cases inject a failure
(database, pipeline, Groq, geocoder, reference data) with unittest.mock.

Used by:
- tests/test_30_address_cases.py  (pytest pass/fail)
- evaluation/run_30_cases.py      (writes the recorded results report)
"""
import socket
import sys
import time
import types
from contextlib import ExitStack
from unittest import mock

from sqlalchemy.exc import OperationalError

VERIFIED = "VERIFIED"
NCC = "NEEDS CUSTOMER CONFIRMATION"
WARNING = "VALIDATION WARNING"
FAILED = "VALIDATION FAILED"

CASES = [
    # ---------------- Valid addresses ----------------
    {"id": "V01", "category": "Valid address",
     "input": "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
     "expect": {"status": 201, "decision": VERIFIED, "min_confidence": 80},
     "why": "Complete Hyderabad address; PIN, city, state and locality all agree in the India Post data."},
    {"id": "V02", "category": "Valid address",
     "input": "Kavya Nair, Flat 806, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678",
     "expect": {"status": 201, "decision": VERIFIED, "no_corrections": True},
     "why": "Complete Bengaluru flat address with no spelling errors; no corrections should be invented."},
    {"id": "V03", "category": "Valid address",
     "input": "Suresh Iyer, 14 Anna Salai, T Nagar, Chennai, Tamil Nadu, 600017, 9840012345",
     "expect": {"status": 201, "decision": VERIFIED},
     "why": "Complete Chennai address; 'Salai' is a Tamil street word and PIN 600017 is in Tamil Nadu."},
    {"id": "V04", "category": "Valid address (formatting variant)",
     "input": "Meera Rao, H.No 7-4-20, Road No. 5, Madhapur, Hyderabad, Telangana, 500 081, 9876543211",
     "expect": {"status": 201, "decision": VERIFIED, "pin": "500081"},
     "why": "A PIN written with a space ('500 081') is a formatting variant and must be normalised, not rejected."},

    # ---------------- Spelling errors ----------------
    {"id": "S01", "category": "Spelling errors (city/state)",
     "input": "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655",
     "expect": {"status": 201, "decision": NCC, "corrections": {"city": "Hyderabad", "state": "Telangana"}},
     "why": "Misspelt city and state are suggested for review, not silently applied."},
    {"id": "S02", "category": "Spelling errors (locality)",
     "input": "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655",
     "expect": {"status": 201, "decision": NCC,
                "corrections": {"locality": "Koramangala", "city": "Bengaluru", "state": "Karnataka"}},
     "why": "Three geographic misspellings are each suggested with the reference spelling."},
    {"id": "S03", "category": "Spelling errors (street)",
     "input": "Sana Ali, H.No 4-1-12, 3rd Main Rod, Indranagar, Banglore, Karnatka, 560038, 9012345678",
     "expect": {"status": 201, "decision": NCC, "correction_fields": ["street", "locality", "city", "state"]},
     "why": "Street-word typo ('Rod') and geographic typos are all offered as corrections."},
    {"id": "S04", "category": "Spelling errors (landmark)",
     "input": "Suresh Rao, H.No 3-4-8, Opposit Metro Staton, Madhapur, Hyderabad, Telangana, 500081, 9876543212",
     "expect": {"status": 201, "decision": NCC, "correction_fields": ["landmark"]},
     "why": "Landmark typos are suggested; the address stays pending until the user decides."},
    {"id": "S05", "category": "Correction approval and re-validation",
     "input": "Arjun Rao, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655",
     "action": "accept_all_and_revalidate",
     "expect": {"status": 200, "decision": VERIFIED, "original_preserved": True, "no_corrections": True},
     "why": "After the user approves every suggestion, all fields are re-validated; the original text is kept for history."},

    # ---------------- Missing / incomplete ----------------
    {"id": "M01", "category": "Missing field (house number)",
     "input": "Priya Reddy, Road No. 5, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
     "expect": {"status": 201, "decision": NCC, "max_confidence": 79, "reason_contains": "Missing house/flat number"},
     "why": "Missing data is uncertainty: the customer is asked to confirm, and confidence is capped."},
    {"id": "M02", "category": "Missing field (PIN)",
     "input": "Ravi Kumar, House 12, 5th Cross Road, Koramangala, Bengaluru, Karnataka, 9988776655",
     "expect": {"status": 201, "decision": NCC, "reason_contains": "PIN code is missing"},
     "why": "No PIN supplied; the address is plausible but cannot be verified."},
    {"id": "M03", "category": "Incomplete address (city and state only)",
     "input": "Hyderabad, Telangana",
     "expect": {"status": 201, "decision": NCC, "max_confidence": 79},
     "why": "Only a city and state: too little to verify, but not evidence of an invalid address."},

    # ---------------- Invalid PIN codes ----------------
    {"id": "P01", "category": "Invalid PIN (wrong length)",
     "input": "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 50008, 9876543210",
     "expect": {"status": 201, "decision": NCC, "stage": ("PIN Validation", "Failed", "expected 6 digits")},
     "why": "A 5-digit PIN is a formatting error, reported as such, not as a missing PIN or a geographic conflict."},
    {"id": "P02", "category": "Invalid PIN (starts with 0)",
     "input": "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 012345, 9876543210",
     "expect": {"status": 201, "decision": NCC, "stage": ("PIN Validation", "Failed", "cannot start with 0")},
     "why": "Indian PIN codes start with 1-9; a leading 0 is a format error."},
    {"id": "P03", "category": "Invalid PIN (placeholder)",
     "input": "Unknown Person, Road 99, Unknown Colony, Hyderabad, Telangana, 999999, 0000000000",
     "expect": {"status": 201, "decision": WARNING},
     "why": "A repeated-digit placeholder PIN plus an invalid phone is concrete evidence that needs manual review."},

    # ---------------- Geographic mismatches ----------------
    {"id": "G01", "category": "Geographic mismatch (city vs state)",
     "input": "Suresh Iyer, 14 Anna Salai, T Nagar, Chennai, Maharashtra, 600017, 9840012345",
     "expect": {"status": 201, "decision": WARNING, "max_confidence": 50, "reason_contains": "Tamil Nadu"},
     "why": "Chennai and PIN 600017 are in Tamil Nadu; the stated state conflicts with reference data."},
    {"id": "G02", "category": "Geographic mismatch (PIN vs state)",
     "input": "Ravi Kumar, House 12, 5th Cross Road, Koramangala, Bengaluru, Telangana, 560034, 9988776655",
     "expect": {"status": 201, "decision": WARNING},
     "why": "PIN 560034 belongs to Karnataka, not Telangana."},
    {"id": "G03", "category": "Geographic mismatch (PIN vs city)",
     "input": "Kavya Nair, Flat 806, Maple Crest Towers, 4th Main Road, Indiranagar, Hyderabad, Telangana, 560038, 9012345678",
     "expect": {"status": 201, "decision": WARNING},
     "why": "PIN 560038 is a Bengaluru PIN but the address names Hyderabad, Telangana."},

    # ---------------- Unusual / ambiguous ----------------
    {"id": "U01", "category": "Unusual format (WhatsApp message)",
     "input": "pls deliver to neha, house 45 sector 21 gurgaon haryana 122016 ph 98100 12345",
     "expect": {"status": 201, "decision": NCC, "not_decision": FAILED},
     "why": "Informal text is parsed; it is incomplete (no locality) but clearly an address."},
    {"id": "U02", "category": "Unusual input (mixed script)",
     "input": "राहुल शर्मा, Flat 5, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9876543210",
     "expect": {"status": 201, "decision_in": [VERIFIED, NCC]},
     "why": "A Devanagari name must not make an otherwise valid address fail."},

    # ---------------- Empty input / unexpected characters / security ----------------
    {"id": "E01", "category": "Empty input",
     "input": "   ",
     "expect": {"status": 400, "error_type": "INPUT_ERROR"},
     "why": "Whitespace-only submissions are rejected with a clear message before any validation runs."},
    {"id": "E02", "category": "Unexpected characters only",
     "input": "@@@ ### !!! ***",
     "expect": {"status": 400, "error_type": "INPUT_ERROR"},
     "why": "Input without any letters or digits cannot be an address."},
    {"id": "E03", "category": "Excessively long input",
     "input": "Flat 1, MG Road, Bengaluru, Karnataka, 560001. " * 40,
     "expect": {"status": 400, "error_type": "INPUT_ERROR"},
     "why": "Inputs over 1000 characters are rejected instead of being processed."},
    {"id": "E04", "category": "Malformed request body",
     "raw_body": "this is not json",
     "expect": {"status": 400, "json_error": True},
     "why": "A non-JSON body returns a JSON error, not an HTML error page or a crash."},
    {"id": "E05", "category": "Injection attempt",
     "input": "'; DROP TABLE validations; -- <script>alert(1)</script>",
     "expect": {"status": 201, "decision": FAILED, "table_intact": True, "raw_echo": True},
     "why": "SQL/HTML in the input is stored as plain text through the ORM; the table survives and the text is echoed verbatim."},

    # ---------------- Database / external service failures ----------------
    {"id": "F01", "category": "Database failure",
     "input": "Rahul Sharma, H.No. 2-4-16, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
     "fault": "db_commit",
     "expect": {"status": 503, "error_type": "TECHNICAL_FAILURE"},
     "why": "If the result cannot be saved, the user gets a retryable technical error, not a crash or a false decision."},
    {"id": "F02", "category": "Validation pipeline failure",
     "input": "Rahul Sharma, H.No. 2-4-17, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
     "fault": "pipeline_crash",
     "expect": {"status": 503, "error_type": "TECHNICAL_FAILURE"},
     "why": "An internal error is reported as a temporary technical failure, never as VALIDATION FAILED."},
    {"id": "F03", "category": "AI service (Groq) failure",
     "input": "Kavya Nair, Flat 807, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678",
     "fault": "groq_error",
     "expect": {"status": 201, "decision": VERIFIED, "stage": ("AI Address Understanding", "Fallback", "")},
     "why": "When the LLM API errors, the deterministic parser takes over and validation still completes."},
    {"id": "F04", "category": "External geocoder timeout",
     "input": "Kavya Nair, Flat 808, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678",
     "fault": "geocoding_timeout",
     "expect": {"status": 201, "decision": VERIFIED,
                "stage": ("External Geocoding Verification", "Fallback", "unavailable")},
     "why": "A geocoder timeout is reported as unavailable and the local India Post data is used; it is not evidence against the address."},
    {"id": "F05", "category": "Reference dataset unavailable",
     "input": "Kavya Nair, Flat 809, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678",
     "fault": "reference_unavailable",
     "expect": {"status": 201, "not_decision": VERIFIED, "reason_contains": "Verification incomplete"},
     "why": "Without the reference data the checks cannot complete, so the address must not be marked VERIFIED."},
]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def make_client(db_path):
    """Create the real Flask app on a temporary SQLite database and log in."""
    from app import create_app
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "TESTING": True,
        "GROQ_API_KEY": "",
        "GEOCODING_ENABLED": False,
        "SECRET_KEY": "test-suite",
    })
    client = app.test_client()
    r = client.post("/api/auth/register", json={"name": "Case Runner", "email": "cases@test.local", "password": "cases-pass"})
    if r.status_code not in (201, 409):
        raise RuntimeError(f"could not register test user: {r.status_code}")
    client.post("/api/auth/login", json={"email": "cases@test.local", "password": "cases-pass"})
    return app, client


class _FailingOpenAI:
    def __init__(self, **kwargs):
        def create(**_):
            raise ConnectionError("simulated Groq outage")
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))


def _fault_context(stack, fault, app):
    from models import db
    if fault == "db_commit":
        stack.enter_context(mock.patch.object(
            db.session, "commit",
            side_effect=OperationalError("INSERT", {}, Exception("simulated database outage"))))
    elif fault == "pipeline_crash":
        stack.enter_context(mock.patch("routes.api.run_pipeline", side_effect=RuntimeError("simulated crash")))
    elif fault == "groq_error":
        stack.enter_context(mock.patch.dict(app.config, {"GROQ_API_KEY": "test-key-not-real"}))
        stack.enter_context(mock.patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=_FailingOpenAI)}))
    elif fault == "geocoding_timeout":
        stack.enter_context(mock.patch.dict(app.config, {"GEOCODING_ENABLED": True}))
        stack.enter_context(mock.patch(
            "services.geocoding_service.urllib.request.urlopen", side_effect=socket.timeout("timed out")))
    elif fault == "reference_unavailable":
        stack.enter_context(mock.patch(
            "services.location_verifier.get_reference_status",
            return_value={"error": "FileNotFoundError", "india_post_rows": 0, "lgd_village_rows": 0}))


def _stage(payload, name):
    for stage in payload.get("pipeline") or []:
        if stage.get("stage") == name:
            return stage
    return {}


def _all_reasons(payload):
    ex = payload.get("explainability") or {}
    return " | ".join(str(x) for x in (ex.get("decision_explanation") or []) + (ex.get("geo_issues") or []))


def run_case(case, app, client):
    """Execute one case. Returns a result record (never raises for a failed expectation)."""
    from models.validation import Validation
    expect = case["expect"]
    started = time.perf_counter()
    with ExitStack() as stack, app.app_context():
        _fault_context(stack, case.get("fault"), app)
        before = Validation.query.count()
        if "raw_body" in case:
            response = client.post("/api/validate", data=case["raw_body"], content_type="text/plain")
        else:
            response = client.post("/api/validate", json={"raw_address": case["input"]})
        payload = response.get_json(silent=True) or {}
        if case.get("action") == "accept_all_and_revalidate" and response.status_code in (200, 201):
            accepted = [{"field": c["field"], "original": c["original"], "suggested": c["suggested"]}
                        for c in payload.get("corrections") or []]
            response = client.post(f"/api/revalidate/{payload['validation_id']}",
                                   json={"accepted": accepted, "rejected": []})
            payload = response.get_json(silent=True) or {}
        after = Validation.query.count()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    failures = []
    if response.status_code != expect["status"]:
        failures.append(f"HTTP {response.status_code}, expected {expect['status']}")
    decision = payload.get("decision")
    if "decision" in expect and decision != expect["decision"]:
        failures.append(f"decision {decision!r}, expected {expect['decision']!r}")
    if "decision_in" in expect and decision not in expect["decision_in"]:
        failures.append(f"decision {decision!r} not in {expect['decision_in']}")
    if "not_decision" in expect and decision == expect["not_decision"]:
        failures.append(f"decision must not be {expect['not_decision']!r}")
    if "error_type" in expect and payload.get("error_type") != expect["error_type"]:
        failures.append(f"error_type {payload.get('error_type')!r}, expected {expect['error_type']!r}")
    if expect.get("json_error") and not (response.is_json and payload.get("error")):
        failures.append("expected a JSON error body")
    confidence = payload.get("confidence")
    if "min_confidence" in expect and (confidence is None or confidence < expect["min_confidence"]):
        failures.append(f"confidence {confidence} < {expect['min_confidence']}")
    if "max_confidence" in expect and (confidence is None or confidence > expect["max_confidence"]):
        failures.append(f"confidence {confidence} > {expect['max_confidence']}")
    if "pin" in expect and (payload.get("parsed_data") or {}).get("pin_code") != expect["pin"]:
        failures.append(f"PIN parsed as {(payload.get('parsed_data') or {}).get('pin_code')!r}")
    corrections = payload.get("corrections") or []
    by_field = {c.get("field"): c.get("suggested") for c in corrections}
    for field, suggested in (expect.get("corrections") or {}).items():
        if by_field.get(field) != suggested:
            failures.append(f"{field} correction {by_field.get(field)!r}, expected {suggested!r}")
    for field in expect.get("correction_fields") or []:
        if field not in by_field:
            failures.append(f"no {field} correction suggested")
    if expect.get("no_corrections") and corrections:
        failures.append(f"unexpected corrections: {[c.get('field') for c in corrections]}")
    if "reason_contains" in expect and expect["reason_contains"] not in _all_reasons(payload):
        failures.append(f"reasons do not mention {expect['reason_contains']!r}")
    if "stage" in expect:
        name, status, text = expect["stage"]
        stage = _stage(payload, name)
        if stage.get("status") != status or text.lower() not in str(stage.get("details", "")).lower():
            failures.append(f"stage {name}: {stage.get('status')!r} / {stage.get('details')!r}")
    if expect.get("original_preserved") and payload.get("original_address") != case["input"]:
        failures.append("original address was not preserved")
    if expect.get("table_intact") and after != before + 1:
        failures.append(f"validations table row count {before} -> {after}")
    if expect.get("raw_echo") and payload.get("raw_address") != case["input"].strip():
        failures.append("raw address was not echoed verbatim")

    ex = payload.get("explainability") or {}
    reasons = ex.get("decision_explanation") or []
    actual = {
        "http_status": response.status_code,
        "decision": decision,
        "confidence": confidence,
        "risk_level": payload.get("risk_level"),
        "rule": ex.get("decision_rule"),
        "error": payload.get("error"),
        "first_reasons": reasons[:3],
    }
    return {
        "id": case["id"],
        "category": case["category"],
        "input": (case.get("input") if "input" in case else f"<raw body> {case['raw_body']}"),
        "expected": expect,
        "actual": actual,
        "passed": not failures,
        "failures": failures,
        "explanation": case["why"],
        "time_ms": elapsed_ms,
    }
