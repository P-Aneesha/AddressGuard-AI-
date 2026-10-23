"""Spelling the AI extractor fixed on its own is still offered for human review."""
from types import SimpleNamespace

from services import pipeline_orchestrator
from services.pipeline_orchestrator import run_pipeline

CFG = SimpleNamespace(GROQ_API_KEY="test-key", GROQ_BASE_URL="", GROQ_MODEL="test-model", GROQ_TIMEOUT_SECONDS=1)
RAW = "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655"


def _fake_ai_extraction(raw_text, *args):
    parsed = {
        "name": "Arjun Kumar", "phone": "9988776655", "house_number": "", "flat_unit": "Flat 302",
        "building": "Green Heights Apartments", "street": "12th Lane", "landmark": "",
        "locality": "Kondapur", "city": "Hyderabad", "district": "", "state": "Telangana",
        "pin_code": "500084", "unrecognized_text": [],
    }
    return parsed, {"source": "ai", "model": "test-model", "status": "Completed"}


def test_ai_respelled_fields_become_pending_corrections(monkeypatch):
    monkeypatch.setattr(pipeline_orchestrator, "extract_with_ai", _fake_ai_extraction)
    monkeypatch.setattr(pipeline_orchestrator, "generate_ai_corrections",
                        lambda *a, **k: ([], {"source": "ai", "status": "Completed"}))
    monkeypatch.setattr(pipeline_orchestrator, "verify_geocoding",
                        lambda *a, **k: {"status": "SKIPPED", "source": "test", "checks": {}})

    result = run_pipeline(RAW, CFG)

    suggestions = {c["field"]: (c["original"].lower(), c["suggested"]) for c in result["corrections"]}
    assert suggestions.get("city") == ("hydrabad", "Hyderabad")
    assert suggestions.get("state") == ("telengana", "Telangana")
    assert suggestions.get("building", ("", ""))[1] == "Green Heights Apartments"
    assert result["decision"] != "VERIFIED"


def test_formatting_only_changes_are_not_corrections():
    det = {"street": "12th Ln", "city": "Hyderabad"}
    ai = {"street": "12th Lane", "city": "Hyderabad"}
    assert pipeline_orchestrator._ai_rewritten_fields(ai, det, "Flat 1, 12th Ln, Hyderabad") == {}
