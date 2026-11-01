"""Addresses written in Indian scripts."""
from types import SimpleNamespace
from unittest import mock

from services import pipeline_orchestrator
from services.script_service import detect_script, normalize_digits

TELUGU = "రవి కుమార్, ఫ్లాట్ 302, సాయి రెసిడెన్సీ, హైటెక్ సిటీ రోడ్, మాదాపూర్, హైదరాబాద్, తెలంగాణ 500081, 9876543210"
ENGLISH = "Ravi Kumar, Flat 302, Sai Residency, Hitech City Road, Madhapur, Hyderabad, Telangana 500081, 9876543210"
CFG = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="test-model", GROQ_TIMEOUT_SECONDS=5)


def test_script_detection_and_digits():
    assert detect_script(TELUGU) == "Telugu"
    assert detect_script("रवि, हैदराबाद").startswith("Devanagari")
    assert detect_script(ENGLISH) is None
    assert normalize_digits("५०००८१ / ౫౦౦౦౮౧ / ௫") == "500081 / 500081 / 5"


def test_without_ai_the_user_is_asked_for_english():
    result = pipeline_orchestrator.run_pipeline(TELUGU, CFG)
    assert result["decision"] == "NEEDS CUSTOMER CONFIRMATION"
    assert result["raw_address"] == TELUGU  # the original is kept
    assert any("enter it in English" in r for r in result["explainability"]["decision_explanation"])


def test_translated_address_is_checked_but_never_auto_verified():
    with mock.patch.object(pipeline_orchestrator, "translate_address", return_value=(ENGLISH, None)):
        result = pipeline_orchestrator.run_pipeline(TELUGU, CFG)
    assert result["parsed_data"]["locality"] == "Madhapur" and result["parsed_data"]["pin_code"] == "500081"
    assert result["decision"] == "NEEDS CUSTOMER CONFIRMATION"
    assert result["confidence"] <= 90
    assert result["translation"] == {"script": "Telugu", "english": ENGLISH, "error": None}
