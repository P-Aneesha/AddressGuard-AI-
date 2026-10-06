def build_explanation(confidence_result: dict, risk_result: dict, decision_result: dict,
                       geo_result: dict, corrections: list) -> dict:
    def _icon(b):
        if b["points"] == 0 and b["ok"]:
            return "ℹ"
        return "✓" if b["ok"] else "✗"

    confidence_lines = [
        f"{_icon(b)} {b['label']}" + (f" +{b['points']}" if b["points"] else "")
        for b in confidence_result["breakdown"]
    ]

    pending_corrections = [
        c for c in (corrections or [])
        if str(c.get("status", "")).upper()
        not in ("ACCEPTED", "APPLIED", "RESOLVED", "REJECTED")
    ]

    explanation = [
        reason for reason in decision_result["reasons"]
        if "spelling/format correction(s) awaiting confirmation" not in reason
        and "pending items needing customer confirmation" not in reason
    ]

    if pending_corrections:
        explanation.append(
            f"{len(pending_corrections)} spelling/format correction(s) awaiting confirmation"
        )
    elif corrections:
        explanation.append("All selected spelling/format decisions were resolved and revalidated")

    # Never leave the dashboard with an empty/"None reported" decision reason.
    if not explanation:
        decision = str(decision_result.get("decision", "")).upper()
        fallback = {
            "VERIFIED": "Required address components are present and validation evidence is consistent.",
            "NEEDS CUSTOMER CONFIRMATION": "The address is plausible but needs customer confirmation before dispatch.",
            "SUSPICIOUS": "One or more validation checks produced a strong conflict that requires manual review.",
            "FAKE ADDRESS": "The supplied text does not contain enough recognizable address structure to verify it.",
        }
        explanation.append(fallback.get(decision, "Validation completed with review information available above."))

    return {
        "confidence_explanation": confidence_lines,
        "risk_explanation": risk_result["reasons"],
        "decision_explanation": explanation,
        "geo_checks": geo_result["checks"],
        "geo_issues": geo_result["issues"],
        "corrections_found": len(pending_corrections),
    }
