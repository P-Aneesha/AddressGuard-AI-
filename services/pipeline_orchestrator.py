from services.ai_address_service import extract_with_ai
from services.address_parser import parse_address
from services.normalizer import normalize_address
from services.phone_validator import validate_phone
from services.pin_validator import validate_pin
from services.location_verifier import verify_geography
from services.geocoding_service import verify_geocoding
from services.anomaly_detector import detect_anomalies
from services.correction_engine import (
    generate_corrections,
    apply_corrections,
    _same_text,
    _is_structurally_canonical_text,
)
from utils.indian_data import INDIAN_STATES, CITY_STATE_MAP, KNOWN_LOCALITIES
from services.address_resolution_service import resolve_and_rank
from services.official_reference_service import generate_official_correction, generate_reference_correction, get_reference_status, is_state_known, locality_matches
from services.ai_correction_service import generate_ai_corrections
from services.confidence_engine import score_confidence
from services.risk_engine import assess_risk
from services.decision_engine import make_decision
from services.explainability_service import build_explanation


def _stage(name, status, details):
    return {"stage": name, "status": status, "details": details}


def _is_ai_correction_safe(correction, normalized):
    """Reject reverse/unsafe AI spelling suggestions for already-canonical values."""
    if not isinstance(correction, dict):
        return False

    field = str(correction.get("field", "")).strip().lower()
    original = str(correction.get("original", "")).strip()
    suggested = str(correction.get("suggested", "")).strip()

    if not field or not original or not suggested:
        return False

    current = str(normalized.get(field, "") or "").strip()
    if not current or not _same_text(original, current):
        return True

    if field == "state":
        return not (is_state_known(current) or any(_same_text(current, x) for x in INDIAN_STATES))

    if field == "city":
        return not any(_same_text(current, x) for x in CITY_STATE_MAP.keys())

    if field == "locality":
        # A locality/village is considered canonical when the nationwide
        # reference layer recognises it; fall back to the built-in list for
        # deployments that have not yet loaded the large datasets.
        try:
            return not bool(locality_matches(current, state=normalized.get("state", ""), district=normalized.get("district", "")).get("verified"))
        except Exception:
            return not any(_same_text(current, x) for x in KNOWN_LOCALITIES.keys())

    if field in {"building", "street", "landmark", "district"}:
        return not _is_structurally_canonical_text(current)

    return True


def _apply_unrecognized_to_raw(raw_text, accepted):
    effective = raw_text
    for correction in accepted or []:
        if correction.get("field") != "unrecognized_text":
            continue
        original = str(correction.get("original", "")).strip()
        suggested = str(correction.get("suggested", "")).strip()
        if original and suggested:
            effective = effective.replace(original, suggested)
    return effective




def _extract_landmark_line(raw_text):
    """Preserve the complete landmark phrase before geographic extraction removes embedded locality names."""
    prefixes = (
        "near", "neer", "opposite", "opposit", "opp", "beside",
        "behind", "next to", "adjacent to", "nearby",
    )
    for raw_line in str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip(" ,;|")
        if not line:
            continue
        low = line.lower()
        if any(
            low == prefix or low.startswith(prefix + " ")
            for prefix in prefixes
        ):
            return line
    return ""

def run_pipeline(raw_text: str, cfg, accepted: list = None, resolved: list = None) -> dict:
    accepted = accepted if isinstance(accepted, list) else []
    resolved = resolved if isinstance(resolved, list) else []
    stages = []
    effective_raw_text = _apply_unrecognized_to_raw(raw_text, accepted)

    # 1. AI Address Understanding
    parsed, ai_meta = extract_with_ai(
        effective_raw_text,
        cfg.GROQ_API_KEY,
        cfg.GROQ_BASE_URL,
        cfg.GROQ_MODEL,
        cfg.GROQ_TIMEOUT_SECONDS,
    )

    if ai_meta["source"] == "ai":
        stages.append(_stage("AI Address Understanding", "Completed", f"Model: {ai_meta['model']}"))
    else:
        stages.append(_stage(
            "AI Address Understanding",
            "Fallback",
            f"Groq unavailable ({ai_meta.get('error', 'no api key')}); used deterministic parser",
        ))

    # 2. Address Parsing
    if ai_meta["source"] != "ai":
        stages.append(_stage(
            "Address Parsing",
            "Completed",
            "Deterministic regex/keyword parser (fallback engine)",
        ))
    else:
        det = parse_address(effective_raw_text)
        filled_ai = sum(1 for key, value in parsed.items() if key != "unrecognized_text" and value)
        stages.append(_stage(
            "Address Parsing",
            "Completed",
            f"AI-extracted fields validated against deterministic parser ({filled_ai} fields found)",
        ))
        parsed.setdefault("unrecognized_text", det.get("unrecognized_text", []))

    # 3. Data Normalization
    normalized = normalize_address(parsed)

    # Preserve a complete free-form landmark line. The parser may first remove
    # a recognized locality such as "Indiranagr" from the landmark segment,
    # leaving only "Opposit Metro Staton". For correction/review we must retain
    # the user's original landmark text as one complete field.
    raw_landmark = _extract_landmark_line(effective_raw_text)
    if raw_landmark:
        normalized_landmark = str(normalized.get("landmark") or "").strip()
        if (
            not normalized_landmark
            or len(raw_landmark.split()) > len(normalized_landmark.split())
            or normalized_landmark.lower() not in raw_landmark.lower()
        ):
            normalized["landmark"] = raw_landmark

    address_fields = (
        "state", "city", "locality", "building", "street", "landmark", "district"
    )
    raw_snapshot = {field: normalized.get(field, "") for field in address_fields}

    # Accepted corrections are applied AFTER AI extraction/normalization so
    # the user's explicit choice always wins over AI re-extraction.
    if accepted:
        normalized = apply_corrections(normalized, accepted)

    stages.append(_stage(
        "Data Normalization",
        "Completed",
        "Whitespace, casing, abbreviation & phone/PIN formatting applied",
    ))

    # 4. Phone Validation
    phone_result = validate_phone(normalized.get("phone", ""))
    stages.append(_stage(
        "Phone Validation",
        "Completed" if phone_result["valid"] else "Warning",
        phone_result["reason"],
    ))

    # 5. PIN Validation
    pin_result = validate_pin(normalized.get("pin_code", ""))
    stages.append(_stage(
        "PIN Validation",
        "Completed" if pin_result["valid"] else "Warning",
        pin_result["reason"],
    ))

    # 6/7/9. Geography
    geo_result = verify_geography(
        normalized.get("city", ""),
        normalized.get("state", ""),
        normalized.get("pin_code", ""),
        normalized.get("locality", ""),
        normalized.get("district", ""),
    )

    cs = geo_result["checks"].get("city_state", "INCOMPLETE")
    stages.append(_stage(
        "City & State Validation",
        "Completed" if cs in ("CONSISTENT", "VERIFIED") else ("Warning" if cs != "INCONSISTENT" else "Failed"),
        f"city_state={cs}",
    ))

    lc = geo_result["checks"].get("locality_city", "INCOMPLETE")
    locality_source = (geo_result.get("official_locality") or {}).get("source") or "project reference"
    stages.append(_stage(
        "Locality Validation",
        "Completed" if lc == "VERIFIED" else ("Warning" if lc != "INCONSISTENT" else "Failed"),
        f"locality_city={lc}; source={locality_source}",
    ))

    # 8. Address Pattern Validation
    has_unit = bool(normalized.get("house_number") or normalized.get("flat_unit"))
    has_street = bool(normalized.get("street"))
    pattern_ok = has_unit and has_street
    stages.append(_stage(
        "Address Pattern Validation",
        "Completed" if pattern_ok else "Warning",
        "House/Flat + Street present" if pattern_ok else "Missing house/flat number or street reference",
    ))

    # 9. Geographic Consistency
    overall_geo = geo_result["overall"]
    ref = geo_result.get("reference", {}) or {}
    ref_detail = (
        f"overall={overall_geo}; India Post rows={ref.get('india_post_rows', 0):,}; "
        f"LGD village rows={ref.get('lgd_village_rows', 0):,}"
    )
    if geo_result["issues"]:
        ref_detail += f"; issues={geo_result['issues']}"
    stages.append(_stage(
        "Geographic Consistency",
        "Completed" if overall_geo == "VERIFIED" else ("Warning" if overall_geo == "LIKELY_MATCH" else "Failed"),
        ref_detail,
    ))

    # Optional external geocoding verification. It is independent from the
    # reference-dataset checks above and is never required for the pipeline to run.
    geocoding_result = verify_geocoding(
        normalized,
        enabled=bool(getattr(cfg, "GEOCODING_ENABLED", False)),
        url=getattr(cfg, "GEOCODING_URL", "https://nominatim.openstreetmap.org/search"),
        timeout=int(getattr(cfg, "GEOCODING_TIMEOUT_SECONDS", 8)),
    )
    stages.append(_stage(
        "External Geocoding Verification",
        "Completed" if geocoding_result["status"] in ("CONFIRMED", "PARTIAL MATCH") else "Warning" if geocoding_result["status"] == "NOT FOUND" else "Fallback",
        f"{geocoding_result['status']} — {geocoding_result['source']}" + (f"; {geocoding_result['reason']}" if geocoding_result.get("reason") else ""),
    ))

    # 10. Anomaly Detection
    anomaly_result = detect_anomalies(normalized, effective_raw_text)
    severity = anomaly_result["severity"]
    stages.append(_stage(
        "Anomaly Detection",
        "Completed" if severity == "NONE" else ("Failed" if severity == "CRITICAL" else "Warning"),
        "; ".join(anomaly_result["reasons"]) or "No anomalies detected",
    ))

    # 11. Context-Aware Address Resolution / Spelling Correction
    # The LLM sees the COMPLETE address and proposes previously unseen spelling
    # corrections. Deterministic reference/fuzzy correction remains a fallback
    # and independent second signal. Nothing is silently applied.
    ai_corrections, ai_correction_meta = generate_ai_corrections(
        effective_raw_text,
        normalized,
        cfg.GROQ_API_KEY,
        cfg.GROQ_BASE_URL,
        cfg.GROQ_MODEL,
        cfg.GROQ_TIMEOUT_SECONDS,
    )
    ai_corrections = [
        correction
        for correction in ai_corrections
        if _is_ai_correction_safe(correction, normalized)
    ]

    # Correction generation must see the user's original field text. The
    # deterministic parser intentionally resolves known geographic misspellings
    # such as Karnatka/Indiranagr for downstream validation, but those originals
    # still need to appear as reviewable suggestions. The parser stores those
    # raw values in _raw_correction_fields for this purpose.
    correction_input = dict(normalized)
    raw_correction_fields = parsed.get("_raw_correction_fields", {}) or {}
    if isinstance(raw_correction_fields, dict):
        for field, raw_value in raw_correction_fields.items():
            raw_value = str(raw_value or "").strip()
            if not raw_value:
                continue
            # The complete landmark line is more faithful than the parser's
            # partially extracted landmark value when it contained a locality.
            if (
                field == "landmark"
                and len(str(correction_input.get("landmark", "")).split())
                > len(raw_value.split())
            ):
                continue
            correction_input[field] = raw_value

    deterministic_corrections = generate_corrections(correction_input)

    # Official postal/LGD reference is a second, independent signal for an
    # otherwise-unrecognized locality/village. This keeps the existing
    # deterministic dictionary while allowing nationwide postal coverage when
    # the official CSVs are installed.
    official_corrections = []
    reference_context = {
        "city": str(normalized.get("city", "") or "").strip(),
        "district": str(normalized.get("district", "") or "").strip(),
        "state": str(normalized.get("state", "") or "").strip(),
        "pin": str(normalized.get("pin_code", "") or "").strip(),
    }
    # Use the complete supplied whole-India reference index for geographic
    # spelling suggestions. This is deliberately a suggestion layer: nothing
    # is applied until the user accepts it.
    for field in ("state", "district", "city", "locality"):
        raw_value = str(correction_input.get(field, "") or "").strip()
        if not raw_value:
            continue
        reference_correction = generate_reference_correction(
            field, raw_value, **reference_context
        )
        if reference_correction:
            official_corrections.append(reference_correction)

    stages.append(_stage(
        "AI Spelling Correction",
        "Completed" if ai_correction_meta.get("source") == "ai" else "Fallback",
        (
            f"{len(ai_corrections)} contextual spelling suggestion(s) generated by {cfg.GROQ_MODEL}"
            if ai_correction_meta.get("source") == "ai"
            else "AI correction unavailable; deterministic spelling correction used as fallback"
        ),
    ))

    # AI suggestions take precedence when they target the same field/value;
    # deterministic suggestions fill gaps when AI has no correction.
    merged = []
    seen = set()
    for correction in ai_corrections + official_corrections + deterministic_corrections:
        key = (
            correction.get("field", "").lower(),
            str(correction.get("original", "")).strip().lower(),
            str(correction.get("suggested", "")).strip().lower(),
        )
        field_key = (correction.get("field", "").lower(), str(correction.get("original", "")).strip().lower())
        if key in seen:
            continue
        # If AI already gave a correction for the same original field value,
        # do not show a competing fuzzy guess.
        if any((c.get("field", "").lower(), str(c.get("original", "")).strip().lower()) == field_key for c in merged):
            continue
        seen.add(key)
        merged.append(correction)

    ranked_corrections = resolve_and_rank(normalized, merged)

    # A human decision resolves a correction for the current review round.
    # Match by field + original OR field + suggested because older frontend
    # payloads sometimes omitted the original value. This prevents accepted
    # and rejected suggestions from being regenerated as pending corrections.
    resolved_original_keys = set()
    resolved_suggested_keys = set()
    for item in resolved:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip().lower()
        original = str(item.get("original", "")).strip().lower()
        suggested = str(item.get("suggested", "")).strip().lower()
        if field and original:
            resolved_original_keys.add((field, original))
        if field and suggested:
            resolved_suggested_keys.add((field, suggested))

    if resolved:
        ranked_corrections = [
            c for c in ranked_corrections
            if (str(c.get("field", "")).strip().lower(), str(c.get("original", "")).strip().lower()) not in resolved_original_keys
            and (str(c.get("field", "")).strip().lower(), str(c.get("suggested", "")).strip().lower()) not in resolved_suggested_keys
        ]

    if ranked_corrections:
        listing = "; ".join(
            f"{c['field'].title()}: {c['original']} → {c['suggested']} ({c['confidence']}%)"
            for c in ranked_corrections
        )
        detail = f"Corrections identified — {listing}"
    elif ai_correction_meta.get("source") == "ai":
        detail = "AI checked the complete address and found no high-confidence spelling correction"
    else:
        detail = "No corrections needed — AI unavailable; deterministic reference/fuzzy fallback found no correction"

    stages.append(_stage(
        "Context-Aware Address Resolution",
        "Warning" if ranked_corrections else "Completed",
        detail,
    ))

    # 12. Confidence & Final Decision
    confidence_result = score_confidence(normalized, phone_result, pin_result, geo_result)

    # An address with unresolved human-review corrections must not receive the
    # same confidence as the final corrected/revalidated address. Keep the
    # evidence score, but cap the review-state confidence until the user has
    # accepted/rejected the suggestions. This also prevents a typo from being
    # displayed as 100% before human confirmation.
    if ranked_corrections:
        confidence_result["score"] = min(94, confidence_result["score"])
        confidence_result["breakdown"].append({
            "ok": True,
            "label": f"{len(ranked_corrections)} unresolved correction(s) pending human review",
            "points": 0,
        })

    # Accepted corrections were successfully applied and re-validated.
    # Give a small explicit confidence improvement for each resolved correction.
    if accepted:
        correction_bonus = min(5, len(accepted))
        confidence_result["score"] = min(
            100,
            confidence_result["score"] + correction_bonus
        )
        confidence_result["breakdown"].append({
            "ok": True,
            "label": f"{correction_bonus} accepted correction(s) successfully re-validated",
            "points": correction_bonus,
        })

    risk_result = assess_risk(
        normalized,
        phone_result,
        pin_result,
        geo_result,
        anomaly_result,
        ranked_corrections,
    )
    decision_result = make_decision(
        normalized,
        confidence_result["score"],
        risk_result,
        geo_result,
        anomaly_result,
        ranked_corrections,
    )
    stages.append(_stage(
        "Confidence & Final Decision",
        "Completed",
        f"confidence={confidence_result['score']}, risk={risk_result['level']}, decision={decision_result['decision']}",
    ))

    explanation = build_explanation(
        confidence_result,
        risk_result,
        decision_result,
        geo_result,
        ranked_corrections,
    )

    output_parsed = dict(normalized)
    for field in address_fields:
        output_parsed[f"raw_{field}"] = raw_snapshot[field]
        output_parsed[f"canonical_{field}"] = normalized.get(field, "")

    return {
        "raw_address": raw_text,
        "effective_raw_address": effective_raw_text,
        "parsed_data": output_parsed,
        "corrections": ranked_corrections,
        "confidence": confidence_result["score"],
        "risk_level": risk_result["level"],
        "decision": decision_result["decision"],
        "pipeline": stages,
        "explainability": explanation,
        "ai_meta": ai_meta,
        "ai_correction_meta": ai_correction_meta,
        "geocoding": geocoding_result,
        "resolved_corrections": resolved,
    }
