"""Optional external geocoding verification.

Disabled by default. Enable with GEOCODING_ENABLED=true and optionally set
GEOCODING_URL. The service never turns a geocoding failure into a fake address;
it reports CONFIRMED, PARTIAL MATCH, NOT FOUND, or UNAVAILABLE.
"""
import json
import logging
import re
import urllib.parse
import urllib.request

from services.official_reference_service import lookup_pincode

logger = logging.getLogger("addressguard.geocoding")


def _clean(v):
    return " ".join(str(v or "").strip().split())


def _similar(a, b):
    import difflib
    a, b = _clean(a).lower(), _clean(b).lower()
    if not a or not b:
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.78


def _query_address(parsed):
    parts = [
        parsed.get("house_number"), parsed.get("flat_unit"), parsed.get("building"),
        parsed.get("street"), parsed.get("locality"), parsed.get("city"),
        parsed.get("district"), parsed.get("state"), parsed.get("pin_code"),
    ]
    return ", ".join(_clean(p) for p in parts if _clean(p))


def _queries(parsed):
    """Generate a small set of increasingly general Nominatim queries."""
    locality = _clean(parsed.get("locality"))
    city = _clean(parsed.get("city"))
    state = _clean(parsed.get("state"))
    district = _clean(parsed.get("district"))
    pin = _clean(parsed.get("pin_code"))
    street = _clean(parsed.get("street"))
    building = _clean(parsed.get("building"))

    queries = []
    # Precise query first, but do not make a failed building/house match fatal.
    full_parts = [
        _clean(parsed.get("house_number")), parsed.get("flat_unit"), building,
        street, locality, city, district, state, pin, "India"
    ]
    full = ", ".join(_clean(p) for p in full_parts if _clean(p))
    if full:
        queries.append(full)

    # Reduced geographic query is much more likely to be indexed in OSM.
    reduced_parts = [locality, city, district, state, pin, "India"]
    reduced = ", ".join(_clean(p) for p in reduced_parts if _clean(p))
    if reduced and reduced != full:
        queries.append(reduced)

    return queries[:2]


def _build_match_result(parsed, item):
    addr = item.get("address", {}) or {}
    city_result = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
    state_result = addr.get("state")
    postcode_result = addr.get("postcode")
    locality_result = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter")
    matches = {
        "city": _similar(parsed.get("city"), city_result),
        "state": _similar(parsed.get("state"), state_result),
        "pin_code": _clean(parsed.get("pin_code")) == _clean(postcode_result),
        "locality": _similar(parsed.get("locality"), locality_result),
    }
    comparable = [v for k, v in matches.items() if parsed.get(k)]
    matched = sum(1 for v in comparable if v)
    if not comparable:
        status = "PARTIAL MATCH"
    elif matched == len(comparable):
        status = "CONFIRMED"
    elif matched > 0:
        status = "PARTIAL MATCH"
    else:
        status = "NOT FOUND"
    return status, matches, matched, len(comparable), city_result, state_result, postcode_result, locality_result


def _postal_fallback(parsed):
    """Use the nationwide India Post snapshot when OSM has no precise result.

    This does not claim the exact building exists. It confirms that the supplied
    PIN belongs to a postal reference whose state/district context is compatible.
    """
    pin = _clean(parsed.get("pin_code"))
    if len(pin) != 6:
        return None
    try:
        rows = lookup_pincode(pin)
    except Exception as exc:
        logger.warning("Postal geocoding fallback failed: %s", exc)
        return None
    if not rows:
        return None

    state = _clean(parsed.get("state"))
    city = _clean(parsed.get("city"))
    locality = _clean(parsed.get("locality"))

    def norm(v):
        return " ".join(re.sub(r"[^a-z0-9]+", " ", _clean(v).lower()).split())

    state_ok = any(norm(state) == norm(r.get("state")) for r in rows) if state else True
    city_ok = False
    if city:
        nc = norm(city)
        for r in rows:
            for value in (r.get("district"), r.get("taluk"), r.get("name")):
                nv = norm(value)
                if nv and (nc == nv or nc in nv or nv in nc):
                    city_ok = True
                    break
            if city_ok:
                break
    else:
        city_ok = True

    good = state_ok and city_ok
    if not good:
        return None

    first = rows[0]
    return {
        "status": "PARTIAL MATCH",
        "source": "India Post postal coordinates (fallback)",
        "coordinates": {
            "lat": first.get("latitude"),
            "lon": first.get("longitude"),
        },
        "display_name": first.get("name", ""),
        "matches": {
            "city": city_ok,
            "state": state_ok,
            "pin_code": True,
            "locality": bool(locality),
        },
        "reason": "Nominatim did not return a precise match; nationwide India Post postal reference matched the PIN and geographic context.",
    }


def verify_geocoding(parsed, enabled=False, url="https://nominatim.openstreetmap.org/search", timeout=8):
    if not enabled:
        return {
            "status": "UNAVAILABLE",
            "source": "External geocoding disabled",
            "coordinates": None,
            "display_name": "",
            "matches": {},
            "reason": "Optional external geocoding is disabled",
        }

    query_list = _queries(parsed)
    if not query_list:
        return {
            "status": "NOT FOUND", "source": "Nominatim/OpenStreetMap",
            "coordinates": None, "display_name": "", "matches": {},
            "reason": "No address content available for geocoding",
        }

    last_reason = "External geocoder returned no result"
    external_error = None
    for query in query_list:
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
                "countrycodes": "in",
            })
            req = urllib.request.Request(
                f"{url}?{params}",
                headers={"User-Agent": "AddressGuard-AI/1.0 research-project"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))

            if not data:
                continue

            item = data[0]
            result = _build_match_result(parsed, item)
            status, matches, matched, comparable_count, *_ = result
            return {
                "status": status,
                "external_status": "AVAILABLE",
                "source": "Nominatim/OpenStreetMap",
                "coordinates": {"lat": item.get("lat"), "lon": item.get("lon")},
                "display_name": item.get("display_name", ""),
                "matches": matches,
                "reason": f"Compared {matched}/{comparable_count} supplied geographic fields" if comparable_count else "No comparable geographic fields",
            }
        except Exception as exc:
            external_error = type(exc).__name__
            last_reason = f"External geocoder unavailable: {external_error}"
            logger.warning("Geocoding query failed: %s", exc)
            break

    # OSM/Nominatim is optional and often has no building-level result for small
    # businesses. Fall back to the nationwide postal reference instead of showing
    # a misleading warning when the postal geography is consistent.
    postal = _postal_fallback(parsed)
    if postal:
        # Keep the external failure visible: this is a local-dataset result,
        # not a confirmation from the external geocoder.
        postal["external_status"] = "UNAVAILABLE" if external_error else "NO RESULT"
        if external_error:
            postal["reason"] = (
                f"External geocoder unavailable ({external_error}); the local India Post "
                "reference matched the PIN and geographic context instead."
            )
        return postal

    if external_error:
        return {
            "status": "UNAVAILABLE", "external_status": "UNAVAILABLE",
            "source": "Nominatim/OpenStreetMap",
            "coordinates": None, "display_name": "", "matches": {},
            "reason": last_reason + "; this is a temporary service limitation, not evidence against the address",
        }

    return {
        "status": "NOT FOUND", "external_status": "NO RESULT", "source": "Nominatim/OpenStreetMap",
        "coordinates": None, "display_name": "", "matches": {},
        "reason": last_reason,
    }
