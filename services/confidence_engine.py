from utils.indian_data import INDIAN_STATES, CITY_STATE_MAP, CITY_ALIASES, KNOWN_LOCALITIES
from services.official_reference_service import is_state_known, locality_matches

def score_confidence(parsed: dict, phone_result: dict, pin_result: dict, geo_result: dict) -> dict:
    """Address-confidence score: how complete and reference-consistent the
    address text is. It is separate from delivery risk (risk_engine)."""
    breakdown = []
    score = 0

    def add(cond, points, pass_label, fail_label=None):
        """fail_label defaults to a negated form of pass_label so a ✗ line never
        reads as if the positive condition were true (e.g. never '✗ House number present')."""
        nonlocal score
        if cond:
            score += points
            breakdown.append({"ok": True, "label": pass_label, "points": points})
        else:
            breakdown.append({"ok": False, "label": fail_label or f"{pass_label} — not provided", "points": 0})

    add(bool(parsed.get("name")), 5, "Name present", "Name not provided")
    add(phone_result.get("valid"), 10, "Valid phone number", "Phone number missing or invalid")

    has_house = bool(parsed.get("house_number"))
    has_flat = bool(parsed.get("flat_unit"))
    # House number and flat/unit are alternatives for the same structural
    # requirement. A flat is a valid unit identifier and must not be penalized
    # simply because a separate house number is absent.
    has_address_number = has_house or has_flat
    add(
        has_address_number,
        10,
        "House/Flat unit identifier provided",
        "House/Flat unit identifier not provided",
    )
    if has_house and has_flat:
        breakdown.append({"ok": True, "label": "House number and Flat/Unit both provided", "points": 0})
    elif has_flat and not has_house:
        breakdown.append({"ok": True, "label": "Flat/Unit is used as the address unit identifier", "points": 0})

    add(bool(parsed.get("street")), 10, "Street/road present", "Street/road not provided")

    locality_value = str(parsed.get("locality") or "").strip()
    locality_recognized = bool(locality_value) and locality_value.lower() in \
        [l.lower() for l in KNOWN_LOCALITIES.keys()]
    if not locality_recognized and locality_value:
        official_locality = locality_matches(
            locality_value,
            city=str(parsed.get("city") or ""),
            district=str(parsed.get("district") or ""),
            state=str(parsed.get("state") or ""),
            pin=str(parsed.get("pin_code") or ""),
        )
        locality_recognized = bool(official_locality.get("verified"))
    add(locality_recognized, 15, "Recognized locality (reference data)", "Locality not recognized in reference data")

    # A city is recognised from the built-in city list/aliases, or when the
    # postal reference rows for the supplied PIN confirm it.
    geo_checks = geo_result.get("checks", {}) or {}
    city_value = str(parsed.get("city") or "").strip().lower()
    known_cities = {c.lower() for c in CITY_STATE_MAP} | {a.lower() for a in CITY_ALIASES}
    city_recognized = bool(city_value) and (
        city_value in known_cities or geo_checks.get("pin_city") == "CONSISTENT"
    )
    add(city_recognized, 15, "Recognized city (reference data)", "City not recognized in reference data")

    state_value = str(parsed.get("state") or "").strip()
    state_valid = bool(state_value) and (state_value.lower() in \
        [s.lower() for s in INDIAN_STATES] or is_state_known(state_value))
    add(state_valid, 10, "Valid state name", "State not recognized/invalid")

    add(pin_result.get("valid"), 10, "Valid 6-digit PIN format",
        "PIN code missing" if pin_result.get("error_type") == "missing" else "PIN code format invalid")
    add(bool(pin_result.get("valid") and pin_result.get("reference_found")), 10,
        "PIN found in postal reference data", "PIN not confirmed by postal reference data")

    consistency_ok = geo_checks and not any(v == "INCONSISTENT" for v in geo_checks.values()) and \
        any(v in ("CONSISTENT", "VERIFIED") for v in geo_checks.values())
    add(consistency_ok, 10, "PIN/city/state geographic consistency", "Geographic consistency not confirmed")

    valid_pattern = bool(parsed.get("street") or has_house or has_flat)
    add(valid_pattern, 5, "Structured address pattern (house/flat or street)", "No house/flat number or street reference")

    max_possible = 5 + 10 + 10 + 10 + 15 + 15 + 10 + 10 + 10 + 10 + 5  # = 110
    normalized = round((score / max_possible) * 100)
    normalized = max(0, min(100, normalized))

    # Caps keep the score consistent with the checks that failed or could not
    # run. Each applied cap is recorded so the change is explained.
    caps = []
    if any(v == "INCONSISTENT" for v in geo_checks.values()):
        caps.append((50, "a reference check reported a geographic conflict"))
    missing = [
        label for label, present in (
            ("house/flat number", has_address_number),
            ("street or locality", bool(parsed.get("street") or parsed.get("locality"))),
            ("city", bool(parsed.get("city"))),
            ("state", bool(parsed.get("state"))),
            ("valid PIN code", bool(pin_result.get("valid"))),
        ) if not present
    ]
    if missing:
        caps.append((79, "essential information is missing or invalid: " + ", ".join(missing)))
    if geo_checks.get("pin_locality") == "DISTANT":
        caps.append((79, "the PIN's post offices are far from the stated locality"))
    reference = geo_result.get("reference") or {}
    if reference.get("error") or (reference and not reference.get("india_post_rows")):
        caps.append((79, "reference verification could not be completed"))
    for limit, why in caps:
        if normalized > limit:
            breakdown.append({"ok": False, "label": f"Confidence capped at {limit}% because {why}", "points": 0})
            normalized = limit

    cap = min([limit for limit, _ in caps], default=100)
    return {"score": normalized, "raw_points": score, "max_points": max_possible, "breakdown": breakdown, "cap": cap}
