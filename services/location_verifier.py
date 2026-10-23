import difflib
import re

from utils.indian_data import (
    CITY_STATE_MAP,
    KNOWN_LOCALITIES,
    CITY_ALIASES,
    LOCALITY_ALIASES,
    STATE_ALIASES,
)

from services.pin_validator import validate_pin

from services.official_reference_service import (
    _canon_state,
    _norm as _norm_ref,
    check_pin_near_locality,
    lookup_pincode,
    locality_matches,
    pin_within_city_area,
    district_state_matches,
    get_reference_status,
    is_state_known,
)


def _similar(a: str, b: str, threshold: float = 0.78) -> bool:
    """Compare geographic names while allowing normal administrative suffixes.

    Example: Bengaluru and Bengaluru Urban are treated as the same geographic
    family for consistency checks, while genuinely different names are not.
    """
    if not a or not b:
        return False

    a = re.sub(r"[^a-z0-9]+", " ", str(a).lower()).strip()
    b = re.sub(r"[^a-z0-9]+", " ", str(b).lower()).strip()

    a = " ".join(a.split())
    b = " ".join(b.split())

    if not a or not b:
        return False

    if a == b or a in b or b in a:
        return True

    # Treat common urban/rural administrative suffixes as non-essential
    # for city-vs-postal-district comparisons (e.g. Bengaluru Urban).
    stripped = []

    for value in (a, b):
        tokens = value.split()

        while tokens and tokens[-1] in {
            "urban",
            "rural",
            "city",
            "south",
            "north",
            "east",
            "west",
            "central",
            "district",
            "division",
            "region",
        }:
            tokens.pop()

        stripped.append(" ".join(tokens))

    a0, b0 = stripped

    if a0 and b0 and (a0 == b0 or a0 in b0 or b0 in a0):
        return True

    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _state_key(value: str) -> str:
    value = STATE_ALIASES.get(str(value or "").strip().lower(), value)
    return re.sub(r"\band\b|\s", "", _norm_ref(_canon_state(value)))


def _same_state(a: str, b: str) -> bool:
    """States match only by canonical name: fuzzy matching would equate
    Andhra Pradesh with Madhya Pradesh (about 79% similar)."""
    return bool(a and b) and _state_key(a) == _state_key(b)


def _canonical(value: str, aliases: dict) -> str:
    value = str(value or "").strip()

    if not value:
        return ""

    return aliases.get(value.lower(), value)


def verify_geography(
    city: str,
    state: str,
    pin_code: str,
    locality: str,
    district: str = "",
) -> dict:

    checks = {}
    issues = []

    city = _canonical(city, CITY_ALIASES)
    state = _canonical(state, STATE_ALIASES)
    locality = _canonical(locality, LOCALITY_ALIASES)
    district = str(district or "").strip()

    expected_state_for_city = CITY_STATE_MAP.get(city)

    if city and state:
        if expected_state_for_city:
            checks["city_state"] = (
                "CONSISTENT"
                if _same_state(expected_state_for_city, state)
                else "INCONSISTENT"
            )

            if checks["city_state"] == "INCONSISTENT":
                issues.append(
                    f"{city} is in {expected_state_for_city}, not {state}"
                )

        elif is_state_known(state):
            checks["city_state"] = "LIKELY_MATCH"

        else:
            checks["city_state"] = "LIKELY_MATCH"

    else:
        checks["city_state"] = "INCOMPLETE"

    if district and state:
        checks["district_state"] = (
            "CONSISTENT"
            if district_state_matches(district, state)
            else "INCONSISTENT"
        )

        if checks["district_state"] == "INCONSISTENT":
            issues.append(
                f"{district} is not mapped to {state} in the available "
                f"LGD/postal reference data"
            )

    else:
        checks["district_state"] = "INCOMPLETE"

    pin_result = validate_pin(pin_code)
    pin_rows = lookup_pincode(pin_code)

    if pin_code and state:
        official_states = {
            str(r.get("state", "")).strip()
            for r in pin_rows
            if r.get("state")
        }

        if official_states:
            checks["pin_state"] = (
                "CONSISTENT"
                if any(_same_state(s, state) for s in official_states)
                else "INCONSISTENT"
            )

            if checks["pin_state"] == "INCONSISTENT":
                issues.append(
                    f"PIN {pin_code} postal reference maps to "
                    f"{sorted(official_states)}, not {state}"
                )

        elif pin_result.get("likely_state"):
            # Only the PIN prefix (postal circle) is known here, so agreement is
            # a likely match rather than confirmation, while disagreement is a
            # concrete conflict worth reporting.
            if _same_state(pin_result["likely_state"], state):
                checks["pin_state"] = "LIKELY_MATCH"
            else:
                checks["pin_state"] = "INCONSISTENT"
                issues.append(
                    f"PIN prefix {str(pin_code)[:2]} belongs to the "
                    f"{pin_result['likely_state']} postal region, not {state}"
                )

        else:
            checks["pin_state"] = (
                "LIKELY_MATCH"
                if pin_result["valid"]
                else "INCOMPLETE"
            )

    else:
        checks["pin_state"] = "INCOMPLETE"

    if pin_code and city:

        if pin_rows:
            places = set()

            for row in pin_rows:
                for key in ("name", "taluk", "district"):
                    if row.get(key):
                        places.add(row[key])

            if any(_similar(x, city) for x in places):
                checks["pin_city"] = "CONSISTENT"
            elif expected_state_for_city and not any(
                _same_state(str(row.get("state", "")), expected_state_for_city)
                for row in pin_rows
            ):
                # The PIN's post offices are all in a different state from the city.
                checks["pin_city"] = "INCONSISTENT"
                if checks.get("pin_state") != "INCONSISTENT":
                    pin_states = sorted({str(row.get("state", "")) for row in pin_rows if row.get("state")})
                    issues.append(f"PIN {pin_code} postal reference maps to {pin_states}, not {city}")
            elif pin_within_city_area(
                pin_code,
                tuple({city, *(alias for alias, canon in CITY_ALIASES.items() if canon == city)}),
                state or expected_state_for_city or "",
            ):
                # A suburb whose post office is in a neighbouring district of the metro area.
                checks["pin_city"] = "CONSISTENT"
            else:
                checks["pin_city"] = "LIKELY_MATCH"

        elif pin_result.get("likely_state") and expected_state_for_city:
            checks["pin_city"] = (
                "LIKELY_MATCH"
                if _same_state(pin_result["likely_state"], expected_state_for_city)
                else "INCONSISTENT"
            )

        else:
            checks["pin_city"] = (
                "LIKELY_MATCH"
                if pin_result["valid"]
                else "INCOMPLETE"
            )

    else:
        checks["pin_city"] = "INCOMPLETE"

    official_locality = {
        "verified": False,
        "candidates": [],
        "reason": "Locality not checked",
        "source": "none",
    }

    if locality and (city or district or state or pin_code):

        official_locality = locality_matches(
            locality,
            city=city,
            district=district,
            state=state,
            pin=pin_code,
        )

        if official_locality.get("verified"):
            checks["locality_city"] = "VERIFIED"

        else:
            # FIX:
            # A locality name can exist in multiple cities.
            # Therefore KNOWN_LOCALITIES must not automatically create
            # a hard conflict when PIN, city and state evidence agree.
            parent = KNOWN_LOCALITIES.get(locality)

            if parent and city:

                parent_matches_city = _similar(parent, city)

                if parent_matches_city:
                    checks["locality_city"] = "VERIFIED"

                elif (
                     checks.get("pin_city") == "CONSISTENT"
                     and checks.get("pin_state") == "CONSISTENT"
                     and checks.get("city_state") == "CONSISTENT"
                     ):
    # PIN + city + state provide strong geographic evidence.
    # A locality name may legitimately exist in multiple cities.
                    checks["locality_city"] = "VERIFIED"
                    checks["locality_city"] = "LIKELY_MATCH"

                else:
                    checks["locality_city"] = "INCONSISTENT"

                    issues.append(
                        f"{locality} conflicts with {city} based on "
                        f"available geographic reference data"
                    )

            elif official_locality.get("strong_candidate"):
                checks["locality_city"] = "LIKELY_MATCH"

            else:
                checks["locality_city"] = "LIKELY_MATCH"

    else:
        checks["locality_city"] = "INCOMPLETE"

    # Near-miss PIN: a real PIN of the right state/city whose post offices are
    # far from the locality. Reported as a warning (customer confirmation),
    # not a hard conflict, because office coordinates can be inaccurate.
    warnings = []
    pin_distance = None
    if locality and pin_code and state and "INCONSISTENT" not in (checks.get("pin_state"), checks.get("pin_city")):
        pin_distance = check_pin_near_locality(locality, city=city, district=district, state=state, pin=pin_code)
        if pin_distance and pin_distance["status"] == "NEAR":
            checks["pin_locality"] = "CONSISTENT"
        elif pin_distance:
            checks["pin_locality"] = "DISTANT"
            warnings.append(
                f"PIN {pin_code} post offices are about {pin_distance['distance_km']:.0f} km from {locality}; "
                f"the post office next to {locality} ({pin_distance['nearby_office']}) uses PIN {pin_distance['nearby_pin']}"
            )

    inconsistent = sum(
        1
        for v in checks.values()
        if v == "INCONSISTENT"
    )

    present_checks = [
        v
        for v in checks.values()
        if v != "INCOMPLETE"
    ]

    # Missing optional hierarchy fields (for example, district omitted from a
    # customer message) do not by themselves turn an otherwise consistent
    # postal/geographic check into a warning.
    overall = (
        "INCONSISTENT"
        if inconsistent > 0
        else (
            "VERIFIED"
            if present_checks
            and all(
                v in ("CONSISTENT", "VERIFIED")
                for v in present_checks
            )
            else "LIKELY_MATCH"
        )
    )

    reference = get_reference_status()

    return {
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "pin_distance": pin_distance,
        "overall": overall,
        "reference": reference,
        "official_locality": (
            official_locality
            if locality
            else {
                "verified": False,
                "candidates": [],
            }
        ),
        "official_pin_rows": pin_rows[:20],
    }