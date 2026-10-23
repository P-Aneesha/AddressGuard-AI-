def assess_risk(parsed: dict, phone_result: dict, pin_result: dict, geo_result: dict,
                 anomaly_result: dict, corrections: list) -> dict:
    reasons = []

    if anomaly_result["severity"] == "CRITICAL":
        return {"level": "CRITICAL", "score": 100,
                "reasons": ["No recognizable address structure (random or non-address text)"] + anomaly_result["reasons"]}

    points = 0
    if not phone_result.get("valid"):
        points += 15; reasons.append("Invalid or missing phone number")
    if not pin_result.get("valid"):
        points += 20; reasons.append(f"Invalid or missing PIN code ({pin_result.get('reason', 'not provided')})")
    if not parsed.get("city"):
        points += 15; reasons.append("City missing")
    if not parsed.get("state"):
        points += 15; reasons.append("State missing")

    issues = geo_result.get("issues", [])
    if issues:
        points += 20 * len(issues)
        reasons.extend(issues)

    if anomaly_result["severity"] == "HIGH":
        points += 30; reasons.extend(anomaly_result["reasons"])
        # Repeated-digit PINs are a concrete high-risk signal. When combined
        # with other invalid credentials, preserve the critical risk level.
        if any("repeated-digit" in str(reason) for reason in anomaly_result.get("reasons", [])):
            points += 15
    elif anomaly_result["severity"] == "MEDIUM":
        points += 15; reasons.extend(anomaly_result["reasons"])

    # Spelling/format suggestions are a review item, not a delivery hazard on
    # their own: capped at 10 points so typos alone can never exceed LOW risk.
    if corrections:
        points += min(10, 5 * len(corrections))
        reasons.append(f"{len(corrections)} unresolved spelling/format correction(s) pending review")

    if not parsed.get("house_number") and not parsed.get("flat_unit"):
        points += 10
        reasons.append("No house number or flat/unit provided")

    if points >= 70:
        level = "CRITICAL"
    elif points >= 40:
        level = "HIGH"
    elif points >= 15:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {"level": level, "score": points, "reasons": reasons}
