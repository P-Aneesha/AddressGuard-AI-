"""Optional Mappls (MapmyIndia) geocoding check.

Mappls has the most complete street-level address data for India, but it is
a paid service: it runs only when MAPPLS_API_KEY is set. The API is documented
at github.com/mappls-api/mappls-rest-apis (mappls-maps-geocoding-rest-api-example):
GET https://search.mappls.com/search/address/geocode?address=...&access_token=KEY,
returning {"copResults": {street, locality, pincode, geocodeLevel,
confidenceScore, eLoc, formattedAddress, ...}}. It returns no coordinates.

The result is informational: it is shown with the validation but does not
change the decision, because its depth and accuracy depend on the plan agreed
with Mappls and it has not been evaluated in this project.
"""
import difflib
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from utils.ai_cache import ResultCache

logger = logging.getLogger("addressguard.mappls")
_CACHE = ResultCache()

GEOCODE_URL = "https://search.mappls.com/search/address/geocode"
# geocodeLevel values that mean Mappls matched the address at street level or finer.
STREET_LEVELS = {"housenumber", "housename", "poi", "street"}


def _clean(value):
    return " ".join(str(value or "").split())


def _similar(a, b, threshold=0.8):
    a, b = _clean(a).lower(), _clean(b).lower()
    return bool(a and b) and (a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= threshold)


def _query(parsed):
    parts = [parsed.get(k) for k in ("house_number", "flat_unit", "building", "street", "locality",
                                     "city", "district", "state", "pin_code")]
    return ", ".join(_clean(p) for p in parts if _clean(p))


def verify_with_mappls(parsed, api_key="", timeout=8):
    """Return {"status", "reason", ...} describing what Mappls found for this address.

    Statuses: NOT CONFIGURED, NOT CHECKED, UNAVAILABLE, NO MATCH, STREET CONFIRMED,
    AREA CONFIRMED (matched above street level), PIN DIFFERS.
    """
    if not api_key:
        return {"status": "NOT CONFIGURED", "reason": "Set MAPPLS_API_KEY to check addresses with Mappls"}
    address = _query(parsed)
    if not address:
        return {"status": "NOT CHECKED", "reason": "No address content to send"}
    cached = _CACHE.get(address)
    if cached is not None:
        return cached
    params = urllib.parse.urlencode({"address": address, "itemCount": 1, "access_token": api_key})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{GEOCODE_URL}?{params}",
                                                           headers={"User-Agent": "AddressGuard-AI/1.0"}),
                                    timeout=timeout) as response:
            status_code, body = response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        reason = {401: "the key is not allowed for this request", 403: "the key's daily/hourly limit was reached"}
        logger.warning("Mappls geocode HTTP %s", exc.code)
        return {"status": "UNAVAILABLE", "reason": f"Mappls returned HTTP {exc.code}"
                + (f": {reason[exc.code]}" if exc.code in reason else "")}
    except Exception as exc:
        logger.warning("Mappls geocode failed: %s", type(exc).__name__)
        return {"status": "UNAVAILABLE", "reason": f"Mappls could not be reached ({type(exc).__name__})"}
    if status_code == 204 or not body.strip():
        result = {"status": "NO MATCH", "reason": "Mappls found no match for this address"}
        _CACHE.put(address, result)
        return result
    try:
        found = json.loads(body).get("copResults")
    except (ValueError, AttributeError):
        return {"status": "UNAVAILABLE", "reason": "Mappls returned an unreadable response"}
    if isinstance(found, list):
        found = found[0] if found else None
    if not isinstance(found, dict):
        result = {"status": "NO MATCH", "reason": "Mappls found no match for this address"}
        _CACHE.put(address, result)
        return result

    level = str(found.get("geocodeLevel") or "")
    mappls_pin = re.sub(r"\D", "", str(found.get("pincode") or ""))
    supplied_pin = re.sub(r"\D", "", str(parsed.get("pin_code") or ""))
    street_match = bool(parsed.get("street")) and _similar(parsed.get("street"), found.get("street"))
    result = {
        "geocode_level": level,
        "confidence": found.get("confidenceScore"),
        "mappls_pin": found.get("eLoc") or found.get("eloc") or "",
        "pincode": mappls_pin,
        "street": found.get("street") or "",
        "formatted_address": found.get("formattedAddress") or "",
    }
    if supplied_pin and mappls_pin and supplied_pin != mappls_pin:
        result.update(status="PIN DIFFERS",
                      reason=f"Mappls places this address in PIN {mappls_pin}, not {supplied_pin}")
    elif level.replace("_", "").lower() in STREET_LEVELS and (street_match or not parsed.get("street")):
        result.update(status="STREET CONFIRMED",
                      reason=f"Mappls matched the address at {level} level: {result['formatted_address']}")
    else:
        result.update(status="AREA CONFIRMED",
                      reason=f"Mappls matched the address only at {level or 'an area'} level"
                             + ("" if street_match else "; the street itself was not confirmed"))
    _CACHE.put(address, result)
    return result
