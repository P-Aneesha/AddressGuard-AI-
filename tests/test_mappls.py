"""Optional Mappls check, with responses shaped like the official API samples."""
import io
import json
import urllib.error
from unittest import mock

from services import mappls_service as mappls

PARSED = {"flat_unit": "Flat 302", "street": "Hitech City Road", "locality": "Madhapur",
          "city": "Hyderabad", "state": "Telangana", "pin_code": "500081"}


def _response(payload, status=200):
    body = json.dumps(payload).encode() if payload is not None else b""
    resp = mock.MagicMock(status=status)
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    return resp


def _check(payload, status=200, key="test-key"):
    mappls._CACHE = mappls.ResultCache()
    with mock.patch.object(mappls.urllib.request, "urlopen", return_value=_response(payload, status)) as call:
        result = mappls.verify_with_mappls(PARSED, key)
    return result, call


def test_not_configured_without_key():
    assert mappls.verify_with_mappls(PARSED, "")["status"] == "NOT CONFIGURED"


def test_street_level_match_confirms_street():
    result, call = _check({"copResults": {"street": "Hitech City Road", "pincode": "500081", "geocodeLevel": "street",
                                          "confidenceScore": 0.8, "eLoc": "ABC123", "formattedAddress": "x"}})
    assert result["status"] == "STREET CONFIRMED" and result["mappls_pin"] == "ABC123"
    url = call.call_args[0][0].full_url
    assert url.startswith(mappls.GEOCODE_URL) and "access_token=test-key" in url


def test_different_pincode_is_reported():
    result, _ = _check({"copResults": [{"street": "", "pincode": "500084", "geocodeLevel": "locality"}]})
    assert result["status"] == "PIN DIFFERS" and "500084" in result["reason"]


def test_area_level_match_and_no_match():
    assert _check({"copResults": {"pincode": "500081", "geocodeLevel": "locality"}})[0]["status"] == "AREA CONFIRMED"
    assert _check(None, status=204)[0]["status"] == "NO MATCH"


def test_quota_error_is_unavailable_and_never_leaks_the_key():
    mappls._CACHE = mappls.ResultCache()
    error = urllib.error.HTTPError(mappls.GEOCODE_URL, 403, "Forbidden", {}, io.BytesIO(b""))
    with mock.patch.object(mappls.urllib.request, "urlopen", side_effect=error):
        result = mappls.verify_with_mappls(PARSED, "secret-key-123")
    assert result["status"] == "UNAVAILABLE" and "limit" in result["reason"]
    assert "secret-key-123" not in json.dumps(result)
