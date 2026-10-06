from types import SimpleNamespace
from flask import Blueprint, request, jsonify, session, send_file, current_app
from sqlalchemy import func
from models import db
from models.validation import Validation
from services.pipeline_orchestrator import run_pipeline
from services.correction_engine import apply_corrections
from services.report_service import generate_pdf, generate_csv, generate_qr, generate_barcode, generate_delivery_qr, build_google_maps_url
from services.official_reference_service import get_reference_status
from services.geocoding_service import verify_geocoding
from utils.timestamps import now_iso

api_bp = Blueprint("api", __name__, url_prefix="/api")

SAMPLE_ADDRESSES = [
    "Rahul Sharma, H.No. 2-4-15, Road No. 3, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
    "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kondapur, Hydrabad, Telengana, 500084, 9988776655",
    "Arjun Kumar, Flat 302, Green Hights Apartments, 12th Lane, Kormangla, Bangaluru, Karnatak, 560034, 9988776655",
    "Kavya Nair, Flat 806, Maple Crest Towers, 4th Main Road, Indiranagar, Bengaluru, Karnataka, 560038, 9012345678",
    "Priya Reddy, Road No. 5, Madhapur, Hyderabad, Telangana, 500081, 9876543210",
    "asdfgh qwerty random address 000000 xyz",
]


def _cfg():
    c = current_app.config
    return SimpleNamespace(
        GROQ_API_KEY=c.get("GROQ_API_KEY", ""), GROQ_BASE_URL=c.get("GROQ_BASE_URL", ""),
        GROQ_MODEL=c.get("GROQ_MODEL", ""), GROQ_TIMEOUT_SECONDS=c.get("GROQ_TIMEOUT_SECONDS", 15),
        GEOCODING_ENABLED=c.get("GEOCODING_ENABLED", False), GEOCODING_URL=c.get("GEOCODING_URL", "https://nominatim.openstreetmap.org/search"),
        GEOCODING_TIMEOUT_SECONDS=c.get("GEOCODING_TIMEOUT_SECONDS", 8),
    )


def _require_login():
    uid = session.get("user_id")
    if not uid:
        return None
    return uid


@api_bp.get("/samples")
def samples():
    return jsonify({"samples": SAMPLE_ADDRESSES})


@api_bp.get("/reference-status")
def reference_status():
    return jsonify(get_reference_status())


@api_bp.post("/validate")
def validate():
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    data = request.get_json(force=True)
    raw = (data.get("raw_address") or "").strip()
    if not raw:
        return jsonify({"error": "raw_address is required"}), 400

    result = run_pipeline(raw, _cfg(), accepted=[])
    v = Validation(
        user_id=uid, raw_address=raw, parsed_data=result["parsed_data"],
        corrections=result["corrections"], confidence=result["confidence"],
        risk_level=result["risk_level"], decision=result["decision"],
        pipeline=result["pipeline"], explainability=result["explainability"],
    )
    db.session.add(v)
    db.session.commit()

    payload = v.to_dict()
    geo_issues = (v.explainability or {}).get("geo_issues", []) if isinstance(v.explainability, dict) else []
    payload["original_address"] = v.raw_address
    payload["final_address_ready"] = (
        v.decision == "VERIFIED"
        and not v.corrections
        and not geo_issues
    )
    payload["corrected_address"] = _format_verified_address(v.parsed_data) if payload["final_address_ready"] else None
    payload["revalidated"] = False
    return jsonify(payload), 201


@api_bp.post("/revalidate/<validation_id>")
def revalidate(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = Validation.query.filter_by(validation_id=validation_id, user_id=uid).first()
    if not v:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True)
    accepted = data.get("accepted", [])
    rejected = data.get("rejected", [])

    if not isinstance(accepted, list) or not isinstance(rejected, list):
        return jsonify({"error": "accepted and rejected must be lists"}), 400

    # Keep correction decisions scoped to this validation record. Accepted and
    # rejected decisions from earlier review rounds remain resolved, while a new
    # validation created through /validate starts with a fresh session.
    prior_resolved = []
    if isinstance(v.explainability, dict):
        prior_resolved = v.explainability.get("_session_resolved_corrections", []) or []
    if not isinstance(prior_resolved, list):
        prior_resolved = []
    resolved = prior_resolved + accepted + rejected

    # IMPORTANT: re-validation must run on the address after the user's accepted
    # changes have actually been applied. Re-running v.raw_address would send the
    # original typo-filled text back through the AI extractor.
    current_parsed = dict(v.parsed_data or {})
    corrected_parsed = apply_corrections(current_parsed, accepted)
    revalidation_raw = _format_revalidation_address(corrected_parsed)

    result = run_pipeline(
        revalidation_raw,
        _cfg(),
        accepted=[],
        resolved=resolved,
    )

    # Safety net for compatibility with older correction payloads.
    original_keys = {
        (str(x.get("field", "")).strip().lower(), str(x.get("original", "")).strip().lower())
        for x in resolved if isinstance(x, dict) and x.get("field") and x.get("original")
    }
    suggested_keys = {
        (str(x.get("field", "")).strip().lower(), str(x.get("suggested", "")).strip().lower())
        for x in resolved if isinstance(x, dict) and x.get("field") and x.get("suggested")
    }
    remaining_corrections = [
        c for c in result.get("corrections", [])
        if (str(c.get("field", "")).strip().lower(), str(c.get("original", "")).strip().lower()) not in original_keys
        and (str(c.get("field", "")).strip().lower(), str(c.get("suggested", "")).strip().lower()) not in suggested_keys
    ]
    result["corrections"] = remaining_corrections

    # Authoritative final pass: an accepted user correction must remain applied
    # even if the AI parser extracts the older spelling again.
    if accepted:
        result["parsed_data"] = apply_corrections(
            dict(result.get("parsed_data") or {}),
            accepted,
        )

    v.parsed_data = result["parsed_data"]
    v.corrections = result["corrections"]
    v.confidence = result["confidence"]
    v.risk_level = result["risk_level"]
    v.decision = result["decision"]
    v.pipeline = result["pipeline"]
    v.explainability = result["explainability"]
    if not isinstance(v.explainability, dict):
        v.explainability = {}
    v.explainability["_session_resolved_corrections"] = resolved
    db.session.commit()

    payload = v.to_dict()
    payload["corrections_applied"] = accepted
    payload["corrections_rejected"] = rejected
    payload["corrections_pending"] = remaining_corrections
    payload["original_address"] = v.raw_address
    payload["geo_issues"] = (v.explainability or {}).get("geo_issues", []) if isinstance(v.explainability, dict) else []
    payload["final_address_ready"] = (
        v.decision == "VERIFIED"
        and not remaining_corrections
        and not payload["geo_issues"]
    )
    payload["corrected_address"] = (
        _format_verified_address(result["parsed_data"])
        if payload["final_address_ready"]
        else None
    )
    payload["revalidated"] = True
    return jsonify(payload)


@api_bp.get("/history")
def history():
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    rows = Validation.query.filter_by(user_id=uid).order_by(Validation.created_at.desc()).limit(100).all()
    return jsonify({"history": [r.to_dict() for r in rows]})


@api_bp.get("/validation/<validation_id>")
def get_validation(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = Validation.query.filter_by(validation_id=validation_id, user_id=uid).first()
    if not v:
        return jsonify({"error": "not found"}), 404
    return jsonify(v.to_dict())


@api_bp.get("/dashboard-stats")
def dashboard_stats():
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    q = Validation.query.filter_by(user_id=uid)
    total = q.count()
    avg_conf = db.session.query(func.avg(Validation.confidence)).filter_by(user_id=uid).scalar() or 0
    decisions = {d: q.filter_by(decision=d).count() for d in
                 ["VERIFIED", "NEEDS CUSTOMER CONFIRMATION", "SUSPICIOUS", "FAKE ADDRESS"]}
    risks = {r: q.filter_by(risk_level=r).count() for r in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]}
    recent = q.order_by(Validation.created_at.desc()).limit(8).all()
    return jsonify({
        "total_validations": total, "average_confidence": round(float(avg_conf), 1),
        "decisions": decisions, "risks": risks,
        "recent": [r.to_dict() for r in recent],
    })



def _format_revalidation_address(parsed):
    """Build a parser-friendly address from the current structured values."""
    parts = [
        parsed.get("name", ""),
        parsed.get("house_number", ""),
        parsed.get("flat_unit", ""),
        parsed.get("building", ""),
        parsed.get("street", ""),
        parsed.get("landmark", ""),
        parsed.get("locality", ""),
        parsed.get("city", ""),
        parsed.get("district", ""),
        parsed.get("state", ""),
        parsed.get("pin_code", ""),
        parsed.get("phone", ""),
    ]
    return ", ".join(str(x).strip() for x in parts if str(x).strip())


def _format_verified_address(parsed):
    parts = [
        parsed.get("house_number", ""),
        parsed.get("flat_unit", ""),
        parsed.get("building", ""),
        parsed.get("street", ""),
        parsed.get("landmark", ""),
        parsed.get("locality", ""),
        parsed.get("city", ""),
        parsed.get("district", ""),
        parsed.get("state", ""),
        parsed.get("pin_code", ""),
    ]
    return ", ".join(str(x).strip() for x in parts if str(x).strip())

@api_bp.get("/evaluation/latest")
def evaluation_latest():
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    import json
    from pathlib import Path
    path = Path(current_app.root_path) / "evaluation" / "evaluation_results.json"
    if not path.exists():
        return jsonify({"status": "NOT_YET_MEASURED", "message": "Accuracy not yet measured — evaluation dataset/testing is still required."})
    try:
        return jsonify(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        return jsonify({"status": "ERROR", "message": f"Could not read evaluation results: {type(exc).__name__}"}), 500


def _get_owned(validation_id, uid):
    return Validation.query.filter_by(validation_id=validation_id, user_id=uid).first()


def _delivery_location_payload(v):
    """Return a delivery navigation target only for a final verified address."""
    parsed = dict(v.parsed_data or {})
    explain = v.explainability if isinstance(v.explainability, dict) else {}
    geo_issues = explain.get("geo_issues", []) or []
    if v.decision != "VERIFIED" or v.corrections or geo_issues:
        return None, ("A final VERIFIED address is required before generating a delivery location.", 409)

    geo = verify_geocoding(
        parsed,
        enabled=bool(getattr(_cfg(), "GEOCODING_ENABLED", False)),
        url=getattr(_cfg(), "GEOCODING_URL", "https://nominatim.openstreetmap.org/search"),
        timeout=int(getattr(_cfg(), "GEOCODING_TIMEOUT_SECONDS", 8)),
    )
    coords = geo.get("coordinates") or {}
    raw_lat = coords.get("lat")
    raw_lon = coords.get("lon")
    exact_coordinates = bool(
        raw_lat not in (None, "")
        and raw_lon not in (None, "")
        and geo.get("source") == "Nominatim/OpenStreetMap"
    )
    # Never turn postal-office fallback coordinates into a building-level
    # navigation target. If OSM did not provide coordinates, use the verified
    # address as a Google Maps search destination instead.
    lat = raw_lat if exact_coordinates else None
    lon = raw_lon if exact_coordinates else None
    address = _format_verified_address(parsed)
    maps_url = build_google_maps_url(lat, lon, address)
    if not maps_url:
        return None, ("Unable to create a Google Maps destination for this address.", 422)

    return {
        "validation_id": v.validation_id,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "maps_url": maps_url,
        "qr_url": f"/api/report/{v.validation_id}/delivery-qr",
        "geocoding_status": geo.get("status"),
        "geocoding_source": geo.get("source"),
        "location_precision": "geocoded" if exact_coordinates else "address search",
        "message": "Google Maps navigation target created from the final verified address." if exact_coordinates else "Google Maps search link created; an exact building-level geocode was not available.",
    }, None


@api_bp.get("/delivery/<validation_id>")
def delivery_location(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    payload, error = _delivery_location_payload(v)
    if error:
        return jsonify({"error": error[0]}), error[1]
    return jsonify(payload)


@api_bp.get("/report/<validation_id>/pdf")
def report_pdf(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    buf = generate_pdf(v.to_dict())
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                      download_name=f"AddressGuard_{validation_id}.pdf")


@api_bp.get("/report/<validation_id>/csv")
def report_csv(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    buf = generate_csv(v.to_dict())
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                      download_name=f"AddressGuard_{validation_id}.csv")


@api_bp.get("/report/<validation_id>/qr")
def report_qr(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    buf = generate_qr(v.to_dict())
    return send_file(buf, mimetype="image/png", as_attachment=True,
                      download_name=f"AddressGuard_{validation_id}_qr.png")


@api_bp.get("/report/<validation_id>/delivery-qr")
def report_delivery_qr(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    payload, error = _delivery_location_payload(v)
    if error:
        return jsonify({"error": error[0]}), error[1]
    buf = generate_delivery_qr(payload["maps_url"])
    return send_file(buf, mimetype="image/png", as_attachment=False,
                     download_name=f"AddressGuard_{validation_id}_delivery_qr.png")


@api_bp.get("/report/<validation_id>/barcode")
def report_barcode(validation_id):
    uid = _require_login()
    if not uid:
        return jsonify({"error": "login required"}), 401
    v = _get_owned(validation_id, uid)
    if not v:
        return jsonify({"error": "not found"}), 404
    buf = generate_barcode(v.to_dict())
    return send_file(buf, mimetype="image/png", as_attachment=True,
                      download_name=f"AddressGuard_{validation_id}_barcode.png")
