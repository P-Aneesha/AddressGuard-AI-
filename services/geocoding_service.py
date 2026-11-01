"""Optional external geocoding verification.

Disabled by default. Enable with GEOCODING_ENABLED=true and optionally set
GEOCODING_URL. The service never turns a geocoding failure into a fake address;
it reports CONFIRMED, PARTIAL MATCH, NOT FOUND, or UNAVAILABLE.
"""
import json
import logging
import math
import re
import threading
import time
import urllib.parse
import urllib.request

from services.official_reference_service import lookup_pincode, street_near_pin
from utils.ai_cache import ResultCache

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
    # The area query (locality, city, state, PIN) is what the comparison uses and
    # is what OpenStreetMap usually has for Indian addresses, so it goes first;
    # the full query with house/building/street is only tried when it is the
    # only query available. Each extra query costs a 1.1 s policy pause.
    full_parts = [
        _clean(parsed.get("house_number")), parsed.get("flat_unit"), building,
        street, locality, city, district, state, pin, "India"
    ]
    full = ", ".join(_clean(p) for p in full_parts if _clean(p))
    reduced_parts = [locality, city, district, state, pin]
    reduced = ", ".join(_clean(p) for p in reduced_parts if _clean(p))
    if reduced:
        queries.append(reduced + ", India")
    elif full:
        queries.append(full)
    return queries


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


_NOMINATIM_LOCK = threading.Lock()
_GEOCODE_CACHE = ResultCache(max_items=1024)
_last_call = [0.0]
STREET_NEAR_KM = 5.0


def _nominatim(url, params, timeout):
    """One Nominatim request, spaced at least 1.1 s from the previous one
    (the public service's usage policy allows one request per second)."""
    with _NOMINATIM_LOCK:
        wait = 1.1 - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "AddressGuard-AI/1.0 research-project"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _km(a, b):
    dx = (b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(b[0] - a[0], dx) * 111.2


def _describe_offline(found, street, city, pin):
    status = found["status"]
    reasons = {
        "FOUND NEAR PIN": f"'{found.get('name')}' is mapped {found.get('distance_km')} km from a post office of PIN {pin}",
        "FOUND ELSEWHERE": f"A road named '{street}' is mapped in the state, but {found.get('distance_km')} km from "
                           f"PIN {pin}; common road names repeat across a city",
        "FOUND IN STATE": f"A road named '{street}' is mapped in the state (the PIN has no coordinates to compare)",
        "NOT IN OPENSTREETMAP": f"'{street}' is not on the OpenStreetMap map near PIN {pin} yet. "
                                "Many Indian streets are not mapped, so this does not affect the decision",
    }
    return {**found, "source": "OpenStreetMap offline road index", "reason": reasons[status]}


def verify_street(parsed, enabled=False, url="https://nominatim.openstreetmap.org/search", timeout=8):
    """Check whether a road of the given name is mapped near the PIN's post offices.

    Informational only: OpenStreetMap's street coverage in India is incomplete
    and generic names ("Main Road") exist everywhere, so the result never
    changes the decision. Statuses: FOUND NEAR PIN, FOUND ELSEWHERE,
    NOT IN OPENSTREETMAP, NOT CHECKED, UNAVAILABLE.
    """
    street, city, state = _clean(parsed.get("street")), _clean(parsed.get("city")), _clean(parsed.get("state"))
    if not street or not (city or parsed.get("locality")):
        return {"status": "NOT CHECKED", "reason": "No street, or no city/locality to search in"}
    # The offline road index (every named road in OpenStreetMap) needs no network.
    offline = street_near_pin(street, state, parsed.get("pin_code", ""))
    if offline is not None:
        return _describe_offline(offline, street, city, parsed.get("pin_code", ""))
    if not enabled:
        return {"status": "NOT CHECKED", "reason": "No offline road index and external geocoding is disabled"}
    pin_points = []
    for row in lookup_pincode(_clean(parsed.get("pin_code"))) if parsed.get("pin_code") else []:
        try:
            pin_points.append((float(row.get("latitude")), float(row.get("longitude"))))
        except (TypeError, ValueError):
            continue
    try:
        data = _nominatim(url, {"street": street, "city": city or _clean(parsed.get("locality")), "state": state,
                                "country": "India", "format": "jsonv2", "addressdetails": 1, "limit": 5}, timeout)
    except Exception as exc:
        logger.warning("Street lookup failed: %s", exc)
        return {"status": "UNAVAILABLE", "reason": f"External geocoder unavailable: {type(exc).__name__}"}
    roads = [d for d in data or [] if _similar((d.get("address") or {}).get("road"), street)]
    if not roads:
        return {"status": "NOT IN OPENSTREETMAP",
                "reason": f"'{street}' is not on the OpenStreetMap map of {city or parsed.get('locality')} yet. "
                          "Many Indian streets are not mapped, so this does not affect the decision"}
    if not pin_points:
        return {"status": "FOUND ELSEWHERE", "reason": f"'{street}' is mapped in {city}, but the PIN has no coordinates to compare"}
    best = min(_km((float(d["lat"]), float(d["lon"])), p) for d in roads for p in pin_points)
    if best <= STREET_NEAR_KM:
        return {"status": "FOUND NEAR PIN", "distance_km": round(best, 1),
                "reason": f"'{street}' is mapped {best:.1f} km from a post office of PIN {parsed.get('pin_code')}"}
    return {"status": "FOUND ELSEWHERE", "distance_km": round(best, 1),
            "reason": f"A road named '{street}' is mapped in {city}, but {best:.0f} km from PIN "
                      f"{parsed.get('pin_code')}; common road names repeat across a city"}


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
            data = _GEOCODE_CACHE.get((url, query))
            if data is None:
                data = _nominatim(url, {"q": query, "format": "jsonv2", "addressdetails": 1,
                                        "limit": 1, "countrycodes": "in"}, timeout)
                _GEOCODE_CACHE.put((url, query), data)

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
