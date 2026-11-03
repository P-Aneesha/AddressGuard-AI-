"""Edge cases found by the 250-address messy evaluation."""
import os

os.environ["GROQ_API_KEY"] = ""
from types import SimpleNamespace

import pytest

from services.address_parser import parse_address
from services.anomaly_detector import detect_anomalies
from services.pipeline_orchestrator import run_pipeline

CFG = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="openai/gpt-oss-20b", GROQ_TIMEOUT_SECONDS=15)


@pytest.mark.parametrize("text", ["test test 123", "1234567890", "lorem ipsum dolor sit amet", "abc 000000"])
def test_junk_text_is_not_an_address(text):
    assert detect_anomalies(parse_address(text), text)["severity"] == "CRITICAL"
    assert run_pipeline(text, CFG)["decision"] == "VALIDATION FAILED"


@pytest.mark.parametrize("text", ["Flat 12, Hyderabad", "12 Gandhi Nagar"])
def test_partial_real_addresses_are_not_junk(text):
    assert detect_anomalies(parse_address(text), text)["severity"] != "CRITICAL"


def test_road_named_post_office_is_the_locality():
    parsed = parse_address("Aditya Rao, Flat 491, Sai Residency, Church Street, Anna Road, Chennai, Tamil Nadu, 600002")
    assert parsed["locality"] == "Anna Road"
    assert parsed["street"] == "Church Street"


def test_ordinary_road_is_not_a_locality():
    parsed = parse_address("Ravi, Flat 2, Lotus Towers, MG Road, Hyderabad, Telangana, 500081")
    assert parsed["street"] == "MG Road" and parsed["locality"] != "MG Road"


@pytest.mark.parametrize("text, field, original", [
    ("Ayesha, 9618528950, Flat 4, Sai Residency, MG Road, Sarojini Nagar, Delhi, Dehli, 110023", "state", "Dehli"),
    ("Sanjay, 6401041900, Flat 9, Shanti Nivas, 2nd Cross Road, Sarojini Nagar, New Delhi, Dehli, 110023", "state", "Dehli"),
    ("Ayesha, 9618528950, Flat 4, Sai Residency, MG Road, Sarojini Nagar, Neww Delhi, Delhi, 110023", "city", "Neww Delhi"),
])
def test_delhi_typos_get_the_right_field(text, field, original):
    result = run_pipeline(text, CFG)
    corrections = {c["field"]: c["original"] for c in result["corrections"]}
    assert corrections.get(field) == original
    assert result["decision"] == "NEEDS CUSTOMER CONFIRMATION"


@pytest.mark.parametrize("label", ["Delivery Address:", "Shipping Address:", "Ship to:", "Deliver to"])
def test_two_word_labels_leave_nothing_unplaced(label):
    result = run_pipeline(f"{label} Rahul Sharma, H.No 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210", CFG)
    assert result["parsed_data"]["unrecognized_text"] == []
    assert result["parsed_data"]["name"] == "Rahul Sharma"
    assert result["decision"] == "VERIFIED"
