"""Street verification is informational and uses distance to the PIN."""
from unittest import mock

import pytest

from services import geocoding_service as geo


@pytest.fixture(autouse=True)
def no_offline_index():
    # These tests cover the live Nominatim path; the offline index is tested separately.
    with mock.patch.object(geo, "street_near_pin", return_value=None):
        yield

PARSED = {"street": "Hitech City Road", "locality": "Madhapur", "city": "Hyderabad",
          "state": "Telangana", "pin_code": "500081"}


def _road(lat, lon, name="Hitech City Road"):
    return {"lat": str(lat), "lon": str(lon), "address": {"road": name}}


def test_street_near_the_pin_is_found_near():
    with mock.patch.object(geo, "_nominatim", return_value=[_road(17.447, 78.38)]):
        result = geo.verify_street(PARSED, enabled=True)
    assert result["status"] == "FOUND NEAR PIN" and result["distance_km"] <= geo.STREET_NEAR_KM


def test_same_name_far_away_is_reported_elsewhere():
    with mock.patch.object(geo, "_nominatim", return_value=[_road(17.30, 78.55)]):
        assert geo.verify_street(PARSED, enabled=True)["status"] == "FOUND ELSEWHERE"


def test_unmapped_street_and_outage_are_not_evidence_against_the_address():
    with mock.patch.object(geo, "_nominatim", return_value=[_road(17.447, 78.38, name="Other Road")]):
        assert geo.verify_street(PARSED, enabled=True)["status"] == "NOT IN OPENSTREETMAP"
    with mock.patch.object(geo, "_nominatim", side_effect=TimeoutError):
        assert geo.verify_street(PARSED, enabled=True)["status"] == "UNAVAILABLE"
    assert geo.verify_street(PARSED, enabled=False)["status"] == "NOT CHECKED"
