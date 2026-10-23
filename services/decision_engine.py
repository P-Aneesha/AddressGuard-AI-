from services.decision_labels import (
    VERIFIED, NEEDS_CONFIRMATION, VALIDATION_WARNING, VALIDATION_FAILED,
)

# Explicit, ordered decision rules. The first rule that matches decides; its id
# and description are returned so every decision can be explained and audited.
DECISION_RULES = {
    "D1": (VALIDATION_FAILED, "No recognisable address structure was found in the input"),
    "D2": (VALIDATION_WARNING, "Critical delivery risk backed by concrete conflicting evidence"),
    "D3": (VALIDATION_WARNING, "A reference dataset reports a hard geographic conflict"),
    "D4": (VALIDATION_WARNING, "High-severity anomaly (e.g. placeholder PIN or mostly unrecognised text)"),
    "D5": (VERIFIED, "All essential components present and every completed reference check is consistent"),
    "D6": (NEEDS_CONFIRMATION, "Plausible address that is incomplete, uncertain or awaiting correction review"),
}

# Evidence phrases that make a CRITICAL risk score a concrete conflict rather
# than an accumulation of missing optional fields.
CONFLICT_TERMS = (
    "repeated-digit", "random", "gibberish", "inconsistent",
    "does not match", "not in", "conflict", "unrecognized",
    "invalid or missing pin", "invalid or missing phone",
)


def _result(rule_id, reasons):
    decision, description = DECISION_RULES[rule_id]
    return {
        "decision": decision,
        "rule": rule_id,
        "rule_description": description,
        "reasons": reasons,
    }


def _reference_limitation(geo_result):
    """Return a human-readable reason when reference verification was not possible."""
    reference = geo_result.get("reference") or {}
    if reference.get("error"):
        return "Reference dataset unavailable, so PIN/locality checks could not be completed"
    if reference and not reference.get("india_post_rows"):
        return "India Post reference data is not loaded, so PIN checks could not be completed"
    return ""


def make_decision(parsed: dict, confidence: int, risk: dict, geo_result: dict,
                  anomaly_result: dict, corrections: list) -> dict:
    """Combine hard evidence first, then completeness and confidence.

    Missing or unverifiable information is treated as uncertainty (D6), never
    as proof that an address is invalid. Only concrete evidence (a reference
    conflict, a placeholder PIN, no address structure at all) produces
    VALIDATION WARNING or VALIDATION FAILED.
    """
    reasons = []
    level = str(risk.get("level", "LOW")).upper()
    anomaly = str(anomaly_result.get("severity", "NONE")).upper()
    geo_issues = geo_result.get("issues", []) or []
    checks = geo_result.get("checks", {}) or {}

    pending = [
        c for c in (corrections or [])
        if str(c.get("status", "")).upper() not in ("ACCEPTED", "APPLIED", "RESOLVED", "REJECTED")
    ]

    # D1. No recognisable address structure at all.
    if anomaly == "CRITICAL":
        reasons.append("Address text has no recognizable structure, so it cannot be validated")
        reasons.extend(anomaly_result.get("reasons", []))
        return _result("D1", reasons)

    # D2. Critical risk, but only when concrete evidence supports it.
    critical_signals = []
    if anomaly in ("HIGH", "MEDIUM"):
        critical_signals.extend(anomaly_result.get("reasons", []))
    critical_signals.extend(geo_issues)
    critical_signals.extend(risk.get("reasons", []))
    has_strong_conflict_signal = any(
        any(term in str(s).lower() for term in CONFLICT_TERMS)
        for s in critical_signals
    )
    if level == "CRITICAL" and has_strong_conflict_signal:
        reasons.append("Critical risk is supported by strong anomaly, validation, or geographic evidence")
        reasons.extend(risk.get("reasons", [])[:5])
        return _result("D2", reasons)

    # D3. A direct reference conflict must not be softened into customer
    # confirmation just because the aggregate risk score happens to be medium.
    hard_geo_conflict = any(
        checks.get(key) == "INCONSISTENT"
        for key in ("city_state", "pin_state", "pin_city", "district_state", "locality_city")
    )
    if geo_issues and (hard_geo_conflict or level in ("HIGH", "CRITICAL")):
        reasons.append("A hard geographic reference conflict was detected; the address requires investigation")
        reasons.extend(geo_issues)
        return _result("D3", reasons)

    # D4. High anomaly, or high risk that is backed by an anomaly. High risk
    # caused only by missing fields falls through to D6 (uncertainty).
    if anomaly == "HIGH" or (level == "HIGH" and anomaly != "NONE"):
        reasons.append("Multiple risk factors present — needs manual review before shipping")
        reasons.extend((anomaly_result.get("reasons", []) + risk.get("reasons", []))[:4])
        return _result("D4", reasons)

    # D5. VERIFIED requires every essential component, a clean geography
    # result, a PIN confirmed against reference data, and no open review items.
    required_core = all([
        bool(parsed.get("name")),
        bool(parsed.get("phone")),
        bool(parsed.get("house_number") or parsed.get("flat_unit")),
        bool(parsed.get("street")),
        bool(parsed.get("locality")),
        bool(parsed.get("city")),
        bool(parsed.get("state")),
        bool(parsed.get("pin_code")),
    ])
    geo_warnings = geo_result.get("warnings", []) or []
    geo_clean = not geo_issues and not geo_warnings and geo_result.get("overall") in ("VERIFIED", "LIKELY_MATCH")
    # The PIN must belong to the stated city as well as the state: a PIN of the
    # right state but another district is a likely delivery mistake.
    pin_confirmed = checks.get("pin_state") == "CONSISTENT" and checks.get("pin_city") in ("CONSISTENT", "INCOMPLETE", None)
    limitation = _reference_limitation(geo_result)

    # Words the parser could not place (e.g. the "Neww" of "Neww Delhi") leave
    # part of the address unexplained, so the address is not fully verified.
    unplaced = [t for t in (parsed.get("unrecognized_text") or []) if str(t).strip()]

    if (required_core and geo_clean and pin_confirmed and not limitation and not unplaced
            and not pending and level == "LOW" and confidence >= 80):
        reasons.append("Required address components are present and validation evidence is consistent")
        if corrections:
            reasons.append("Spelling/format decisions were resolved and the address was revalidated")
        return _result("D5", reasons)

    # D6. Plausible but not fully confirmed.
    reasons.append("Address is plausible but incomplete or has pending items needing customer confirmation")
    if limitation:
        reasons.append(f"Verification incomplete: {limitation}")
    elif checks.get("pin_state") == "CONSISTENT" and checks.get("pin_city") == "LIKELY_MATCH":
        reasons.append("The PIN's post offices are in the right state but not in the stated city or its district")
    elif parsed.get("pin_code") and not pin_confirmed and checks.get("pin_state") != "INCOMPLETE":
        reasons.append("PIN code could not be confirmed against the available postal reference data")
    if not parsed.get("house_number") and not parsed.get("flat_unit"):
        reasons.append("Missing house/flat number")
    if not parsed.get("phone"):
        reasons.append("Phone number is missing or could not be validated")
    if not parsed.get("pin_code"):
        reasons.append("PIN code is missing")
    if not parsed.get("locality"):
        reasons.append("Locality is missing")
    if not parsed.get("city"):
        reasons.append("City is missing or could not be identified")
    if not parsed.get("state"):
        reasons.append("State is missing or could not be identified")
    if not parsed.get("street"):
        reasons.append("Street/road reference is missing")
    if checks.get("locality_city") == "LIKELY_MATCH":
        reasons.append("Locality could not be fully verified against the reference data")
    if level in ("HIGH", "CRITICAL"):
        reasons.append(f"Delivery risk is {level} because several details are missing; this is uncertainty, not proof of an invalid address")
    if pending:
        reasons.append(f"{len(pending)} spelling/format correction(s) awaiting confirmation")
    if unplaced:
        reasons.append("Some text could not be matched to any address field: " + ", ".join(map(str, unplaced[:3])))
    if geo_issues:
        reasons.extend(geo_issues[:3])
    reasons.extend(geo_warnings[:2])

    return _result("D6", reasons)
