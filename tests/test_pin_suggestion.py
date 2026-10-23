"""A PIN from another state is flagged on PIN-city and gets a reference-backed suggestion."""
from services.location_verifier import verify_geography
from services.official_reference_service import suggest_pin_code


def test_pin_from_another_state_is_inconsistent_with_city():
    result = verify_geography("Hyderabad", "Telangana", "110001", "Madhapur", "")
    assert result["checks"]["pin_state"] == "INCONSISTENT"
    assert result["checks"]["pin_city"] == "INCONSISTENT"


def test_matching_pin_stays_consistent():
    result = verify_geography("Hyderabad", "Telangana", "500081", "Madhapur", "")
    assert result["checks"]["pin_city"] == "CONSISTENT"


def test_pin_suggested_from_nearest_post_office():
    suggestion = suggest_pin_code("Madhapur", city="Hyderabad", state="Telangana")
    assert suggestion["field"] == "pin_code"
    assert suggestion["suggested"] == "500081"


def test_near_miss_pin_in_the_right_city_is_flagged():
    result = verify_geography("Hyderabad", "Telangana", "500001", "Madhapur", "")
    assert result["checks"]["pin_state"] == "CONSISTENT"
    assert result["checks"]["pin_locality"] == "DISTANT"
    assert result["warnings"] and "500081" in result["warnings"][0]
    assert result["issues"] == []  # a warning, not a hard conflict


def test_correct_pin_is_near_its_locality():
    result = verify_geography("Hyderabad", "Telangana", "500081", "Madhapur", "")
    assert result["checks"]["pin_locality"] == "CONSISTENT"
    assert result["warnings"] == []


def test_no_pin_suggestion_without_unambiguous_reference():
    assert suggest_pin_code("Nowhereville Xyz", city="Hyderabad", state="Telangana") is None
    assert suggest_pin_code("Madhapur", city="Hyderabad", state="") is None
