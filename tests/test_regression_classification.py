from services.official_reference_service import locality_matches


def test_peerzadiguda_is_verified_from_reference_data():
    result = locality_matches(
        "Peerzadiguda",
        city="Hyderabad",
        district="MEDCHAL MALKAJGIRI",
        state="Telangana",
        pin="500039",
    )
    assert result["verified"] is True


def test_indiranagar_uses_pin_and_geographic_context():
    result = locality_matches(
        "Indiranagar",
        city="Bengaluru",
        district="BENGALURU URBAN",
        state="Karnataka",
        pin="560038",
    )
    assert result["verified"] is True
    assert result["candidates"][0]["name"] == "Indiranagar S.O (Bengaluru)"


def test_spelling_variant_gets_candidate_without_silent_change():
    result = locality_matches(
        "Kormangla",
        city="Bengaluru",
        district="BENGALURU URBAN",
        state="Karnataka",
        pin="560034",
    )
    assert result["verified"] is False
    assert result["strong_candidate"]["name"] == "Koramangala S.O"


def test_unknown_urban_area_is_not_declared_invalid_by_reference_lookup():
    # A locality name that no dataset contains: no candidates and no verification,
    # reported as "not supported" rather than as an invalid address.
    result = locality_matches(
        "Qwzx Vihar Colony",
        city="Hyderabad",
        district="Ranga Reddy",
        state="Telangana",
        pin="500070",
    )
    assert result["verified"] is False
    assert result["candidates"] == []
    assert "No sufficiently supported locality match" in result["reason"]


def test_urban_locality_missing_from_postal_data_is_found_in_osm_localities():
    # "B N Reddy Nagar" has no post office of that name; the OpenStreetMap
    # locality layer supplies it as a candidate (spelling differs: "BN").
    result = locality_matches(
        "B N Reddy Nagar",
        city="Hyderabad",
        district="Ranga Reddy",
        state="Telangana",
        pin="500070",
    )
    assert any(c.get("kind") == "osm_locality" and c["name"] == "BN Reddy Nagar" for c in result["candidates"])


import pytest
from types import SimpleNamespace


@pytest.mark.parametrize("raw, street, locality", [
    ("Rohit Gupta, House 21, Ring Road, Lajpat Nagar, New Delhi, Delhi, 110024, 9810012345", "Ring Road", "Lajpat Nagar"),
    ("Anil Patil, Plot 7, Station Road, Peerzadiguda, Hyderabad, Telangana, 500098, 9876543210", "Station Road", "Peerzadiguda"),
    ("Meena Shah, Flat 3, Satyam Towers, CG Road, Navrangpura, Ahmedabad, Gujarat, 380009, 9825012345", "CG Road", "Navrangpura"),
])
def test_reference_localities_are_parsed_and_verified(raw, street, locality):
    from services.pipeline_orchestrator import run_pipeline
    cfg = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="test", GROQ_TIMEOUT_SECONDS=5)
    r = run_pipeline(raw, cfg)
    assert r["parsed_data"]["street"] == street
    assert r["parsed_data"]["locality"] == locality
    assert r["explainability"]["geo_checks"]["locality_city"] == "VERIFIED"
    assert r["decision"] == "VERIFIED"


def test_village_is_verified_by_its_lgd_pin_link():
    result = locality_matches("Peerzadiguda", state="Telangana", pin="500098")
    assert result["verified"] is True
    assert any(c.get("kind") == "village" and c["evidence"]["pin"] for c in result["candidates"])
