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
    lookup_pincode,
    locality_matches,
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
                if _similar(expected_state_for_city, state)
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
                if any(_similar(s, state) for s in official_states)
                else "INCONSISTENT"
            )

            if checks["pin_state"] == "INCONSISTENT":
                issues.append(
                    f"PIN {pin_code} postal reference maps to "
                    f"{sorted(official_states)}, not {state}"
                )

        elif pin_result.get("likely_state"):
            checks["pin_state"] = (
                "CONSISTENT"
                if _similar(pin_result["likely_state"], state)
                else "INCONSISTENT"
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

            checks["pin_city"] = (
                "CONSISTENT"
                if any(_similar(x, city) for x in places)
                else (
                    "CONSISTENT"
                    if expected_state_for_city
                    and any(
                        _similar(
                            str(row.get("state", "")),
                            expected_state_for_city,
                        )
                        for row in pin_rows
                    )
                    and any(
                        _similar(
                            str(row.get("district", "")),
                            city,
                        )
                        or _similar(
                            str(row.get("taluk", "")),
                            city,
                        )
                        for row in pin_rows
                    )
                    else "LIKELY_MATCH"
                )
            )

        elif pin_result.get("likely_state") and expected_state_for_city:
            checks["pin_city"] = (
                "CONSISTENT"
                if _similar(
                    pin_result["likely_state"],
                    expected_state_for_city,
                )
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