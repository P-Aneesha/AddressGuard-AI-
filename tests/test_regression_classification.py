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
    result = locality_matches(
        "B N Reddy Nagar",
        city="Hyderabad",
        district="Ranga Reddy",
        state="Telangana",
        pin="500070",
    )
    assert result["verified"] is False
    assert result["candidates"] == []
    assert "No sufficiently supported locality match" in result["reason"]
