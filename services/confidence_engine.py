from utils.indian_data import INDIAN_STATES, CITY_STATE_MAP, KNOWN_LOCALITIES
from services.official_reference_service import is_state_known, locality_matches

def score_confidence(parsed: dict, phone_result: dict, pin_result: dict, geo_result: dict) -> dict:
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

    city_recognized = bool(parsed.get("city")) and parsed["city"].lower() in \
        [c.lower() for c in CITY_STATE_MAP.keys()]
    add(city_recognized, 15, "Recognized city (reference data)", "City not recognized in reference data")

    state_value = str(parsed.get("state") or "").strip()
    state_valid = bool(state_value) and (state_value.lower() in \
        [s.lower() for s in INDIAN_STATES] or is_state_known(state_value))
    add(state_valid, 10, "Valid state name", "State not recognized/invalid")

    add(pin_result.get("valid"), 20, "Valid 6-digit PIN code", "PIN code missing or invalid")

    geo_checks = geo_result.get("checks", {})
    consistency_ok = geo_checks and not any(v == "INCONSISTENT" for v in geo_checks.values()) and \
        any(v in ("CONSISTENT", "VERIFIED") for v in geo_checks.values())
    add(consistency_ok, 10, "PIN/city/state geographic consistency", "Geographic consistency not confirmed")

    valid_pattern = bool(parsed.get("street") or has_house or has_flat)
    add(valid_pattern, 5, "Structured address pattern (house/flat + street)", "No structured house/flat + street pattern")

    max_possible = sum(b["points"] if b["points"] else 0 for b in breakdown) or 1
    # max_possible above only sums earned points; recompute true ceiling from the rule set:
    max_possible = 5 + 10 + 10 + 10 + 15 + 15 + 10 + 20 + 10 + 5  # = 110
    normalized = round((score / max_possible) * 100)
    normalized = max(0, min(100, normalized))
    return {"score": normalized, "raw_points": score, "max_points": max_possible, "breakdown": breakdown}
