"""Mistakes found in the AI-mode evaluation: typos kept by the AI, a city filed
as the district, and real towns "corrected" to better-known cities."""
from types import SimpleNamespace
from unittest import mock

import pytest

from services import pipeline_orchestrator
from services.pipeline_orchestrator import run_pipeline

CFG = SimpleNamespace(GROQ_API_KEY="test-key", GROQ_BASE_URL="", GROQ_MODEL="test-model", GROQ_TIMEOUT_SECONDS=1)
NO_AI = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="m", GROQ_TIMEOUT_SECONDS=1)
BASE = {"name": "Sneha Gupta", "phone": "9876543210", "house_number": "", "flat_unit": "Flat 784",
        "building": "Sunrise Enclave", "street": "2nd Cross Road", "landmark": "", "unrecognized_text": []}


def _run_with_ai(raw, fields):
    ai = ({**BASE, **fields}, {"source": "ai", "model": "test-model", "status": "Completed"})
    with mock.patch.object(pipeline_orchestrator, "extract_with_ai", return_value=ai), \
            mock.patch.object(pipeline_orchestrator, "generate_ai_corrections",
                              return_value=([], {"source": "ai", "status": "Completed"})):
        return run_pipeline(raw, CFG)


@pytest.mark.parametrize("typo, canonical, city, pin", [
    ("Rajastan", "Rajasthan", "Jaipur", "302016"),
    ("Andhra Pradsh", "Andhra Pradesh", "Tirupati", "524101"),
])
def test_state_typo_kept_by_ai_is_a_correction_not_a_conflict(typo, canonical, city, pin):
    raw = f"Sneha Gupta, Flat 784, Sunrise Enclave, 2nd Cross Road, {city}, {typo}, {pin}, 9876543210"
    result = _run_with_ai(raw, {"locality": "", "city": city, "district": "", "state": typo, "pin_code": pin})
    assert result["parsed_data"]["state"] == canonical
    assert {c["field"]: c["suggested"] for c in result["corrections"]}.get("state") == canonical
    assert result["decision"] == "NEEDS CUSTOMER CONFIRMATION"


def test_city_filed_as_district_by_ai_is_restored():
    raw = "Ananya Rao, Flat 919, Lotus Towers, 2nd Cross Road, Armoor, Niazmabad, Telangana, 503224, 6933212345"
    result = _run_with_ai(raw, {"locality": "", "city": "Armoor", "district": "Niazmabad",
                                "state": "Telangana", "pin_code": "503224"})
    parsed = result["parsed_data"]
    assert (parsed["city"], parsed["locality"], parsed["district"]) == ("Nizamabad", "Armoor", "")
    assert {c["field"]: c["suggested"] for c in result["corrections"]}.get("city") == "Nizamabad"
    assert result["decision"] == "NEEDS CUSTOMER CONFIRMATION"


def test_real_town_is_not_corrected_to_a_bigger_city():
    result = run_pipeline("Pooja Khan, Flat 775, Krishna Complex, Church Street, Gudur, Tirupati, "
                          "Andhra Pradesh, 524101, 9876543210", NO_AI)
    assert "Guntur" not in {c["suggested"] for c in result["corrections"]}
