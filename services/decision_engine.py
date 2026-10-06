def make_decision(parsed: dict, confidence: int, risk: dict, geo_result: dict,
                  anomaly_result: dict, corrections: list) -> dict:
    """Combine hard evidence first, then confidence/completeness.

    Risk is not allowed to override strong fake/anomaly evidence incorrectly,
    but genuine critical suspicious evidence is propagated to SUSPICIOUS.
    Confidence is an evidence score, not the sole classifier.
    """
    reasons = []
    level = str(risk.get("level", "LOW")).upper()
    anomaly = str(anomaly_result.get("severity", "NONE")).upper()
    geo_issues = geo_result.get("issues", []) or []

    pending = [
        c for c in (corrections or [])
        if str(c.get("status", "")).upper() not in ("ACCEPTED", "APPLIED", "RESOLVED", "REJECTED")
    ]

    # 1. Explicit critical anomaly remains the strongest fake/random gate.
    if anomaly == "CRITICAL":
        reasons.append("Address text has no recognizable structure — treated as fake/random")
        reasons.extend(anomaly_result.get("reasons", []))
        return {"decision": "FAKE ADDRESS", "reasons": reasons}

    # 2. Critical risk caused by concrete suspicious evidence should propagate.
    # Do not use CRITICAL alone: inspect the evidence behind the risk score.
    critical_signals = []
    if anomaly in ("HIGH", "MEDIUM"):
        critical_signals.extend(anomaly_result.get("reasons", []))
    critical_signals.extend(geo_issues)
    critical_signals.extend(risk.get("reasons", []))

    suspicious_terms = (
        "repeated-digit", "fake", "random", "gibberish", "inconsistent",
        "does not match", "not in", "conflict", "unrecognized", "invalid or missing pin",
        "invalid or missing phone"
    )
    has_strong_suspicious_signal = any(
        any(term in str(s).lower() for term in suspicious_terms)
        for s in critical_signals
    )

    if level == "CRITICAL" and has_strong_suspicious_signal:
        reasons.append("Critical risk is supported by strong anomaly, validation, or geographic evidence")
        reasons.extend(risk.get("reasons", [])[:5])
        return {"decision": "SUSPICIOUS", "reasons": reasons}

    # 3. Hard geographic conflicts are independently suspicious. A direct
    # reference conflict must not be softened into customer confirmation just
    # because the aggregate risk score happens to be medium.
    hard_geo_checks = geo_result.get("checks", {}) or {}
    hard_geo_conflict = any(
        hard_geo_checks.get(key) == "INCONSISTENT"
        for key in ("city_state", "pin_state", "pin_city", "district_state", "locality_city")
    )
    if geo_issues and (hard_geo_conflict or level in ("HIGH", "CRITICAL")):
        reasons.append("A hard geographic reference conflict was detected; the address requires investigation")
        reasons.extend(geo_issues)
        return {"decision": "SUSPICIOUS", "reasons": reasons}

    # 4. High anomaly/risk with concrete evidence requires review.
    if level == "HIGH" or anomaly == "HIGH":
        reasons.append("Multiple risk factors present — needs manual review before shipping")
        reasons.extend(risk.get("reasons", [])[:3])
        return {"decision": "SUSPICIOUS", "reasons": reasons}

    # 5. A complete, geographically consistent address can be VERIFIED even
    # when optional information (e.g. landmark/flat) is absent.
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
    geo_clean = not geo_issues and geo_result.get("overall") in ("VERIFIED", "LIKELY_MATCH")
    no_pending = not pending

    if required_core and geo_clean and no_pending and level == "LOW" and confidence >= 80:
        reasons.append("Required address components are present and validation evidence is consistent")
        if corrections:
            reasons.append("Spelling/format decisions were resolved and the address was revalidated")
        return {"decision": "VERIFIED", "reasons": reasons}

    # A strong but harmlessly incomplete address remains confirmable rather than suspicious.
    reasons.append("Address is plausible but incomplete or has pending items needing customer confirmation")
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
    if geo_result.get("checks", {}).get("locality_city") == "LIKELY_MATCH":
        reasons.append("Locality could not be fully verified against the reference data")
    if pending:
        reasons.append(f"{len(pending)} spelling/format correction(s) awaiting confirmation")
    if geo_issues:
        reasons.extend(geo_issues[:3])

    return {"decision": "NEEDS CUSTOMER CONFIRMATION", "reasons": reasons}
