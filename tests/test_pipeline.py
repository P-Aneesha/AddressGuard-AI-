import os
os.environ["GROQ_API_KEY"] = ""  # force deterministic fallback parser for reproducible tests
from types import SimpleNamespace
from services.pipeline_orchestrator import run_pipeline

CFG = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="openai/gpt-oss-20b", GROQ_TIMEOUT_SECONDS=15)

def test_complete_valid_address_is_verified():
    r = run_pipeline(
        "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210", CFG)
    assert r["decision"] == "VERIFIED"
    assert r["risk_level"] == "LOW"
    assert r["confidence"] >= 85
    assert r["corrections"] == []

def test_flat_vs_house_number_distinction():
    r = run_pipeline(
        "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655", CFG)
    pd = r["parsed_data"]
    assert pd["flat_unit"].startswith("Flat 302")
    assert pd["house_number"] == ""
    assert "Green Hights" in pd["building"]
    fields = {c["field"] for c in r["corrections"]}
    assert "state" in fields and "city" in fields

def test_multiple_corrections_detected():
    r = run_pipeline(
        "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655", CFG)
    fields = {c["field"]: c["suggested"] for c in r["corrections"]}
    assert fields.get("state") == "Karnataka"
    assert fields.get("city") == "Bengaluru"
    assert fields.get("locality") == "Koramangala"

def test_clean_address_no_unnecessary_corrections():
    r = run_pipeline(
        "Kavya Nair, Flat 806, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678", CFG)
    assert r["corrections"] == []
    assert r["decision"] == "VERIFIED"

def test_missing_house_number_is_not_failed():
    r = run_pipeline(
        "Priya Reddy, Road No. 5, Madhapur, Hyderabad, Telangana, 500081, 9876543210", CFG)
    assert r["decision"] != "VALIDATION FAILED"
    complete = run_pipeline(
        "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210", CFG)
    assert r["confidence"] < complete["confidence"]

def test_random_text_fails_validation():
    r = run_pipeline("asdfgh qwerty random address 000000 xyz", CFG)
    assert r["decision"] == "VALIDATION FAILED"
    assert r["risk_level"] == "CRITICAL"
    assert r["confidence"] < 20

def test_revalidation_after_accepting_corrections():
    raw = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655"
    r1 = run_pipeline(raw, CFG)
    accepted = [{"field": c["field"], "original": c["original"], "suggested": c["suggested"]} for c in r1["corrections"]]
    r2 = run_pipeline(raw, CFG, accepted=accepted, resolved=accepted)
    assert r2["corrections"] == []
    assert r2["decision"] == "VERIFIED"
    assert r2["confidence"] > r1["confidence"]


def test_revalidation_after_rejecting_corrections_keeps_original_and_resolves_review():
    raw = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655"
    r1 = run_pipeline(raw, CFG)
    rejected = [{"field": c["field"], "original": c["original"], "suggested": c["suggested"]} for c in r1["corrections"]]
    r2 = run_pipeline(raw, CFG, accepted=[], resolved=rejected)
    assert r2["corrections"] == []
    assert r2["parsed_data"]["city"] == "Bangaluru" or r2["parsed_data"]["city"] == "Bengaluru"
