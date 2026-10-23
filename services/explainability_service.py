from services.decision_labels import DECISION_DESCRIPTIONS, normalize_decision


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
        decision = normalize_decision(decision_result.get("decision", ""))
        explanation.append(DECISION_DESCRIPTIONS.get(decision, "Validation completed with review information available above."))

    # Name the rule that produced the decision so it can be audited.
    if decision_result.get("rule"):
        explanation.insert(0, f"Rule {decision_result['rule']}: {decision_result.get('rule_description', '')}")

    limitations = [
        "Reference and geocoding checks confirm geographic consistency only; they do not prove that the building exists or guarantee delivery.",
    ]
    reference = geo_result.get("reference") or {}
    if reference.get("error") or (reference and not reference.get("india_post_rows")):
        limitations.append("India Post reference data was unavailable, so PIN and locality checks could not be completed.")
    if reference and reference.get("lgd_village_rows") == 0:
        limitations.append("LGD village data is not installed, so village-level locality checks were not performed.")

    return {
        "confidence_explanation": confidence_lines,
        "risk_explanation": risk_result["reasons"],
        "decision_explanation": explanation,
        "geo_checks": geo_result["checks"],
        "geo_issues": geo_result["issues"],
        "corrections_found": len(pending_corrections),
        "decision_rule": decision_result.get("rule"),
        "limitations": limitations,
    }
