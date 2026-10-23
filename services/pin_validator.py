import re
from utils.indian_data import PIN_PREFIX_TO_STATE, PIN_REFERENCE
from services.official_reference_service import lookup_pincode


def _official_to_pin_info(rows, pin):
    states = sorted({str(r.get("state", "")).strip() for r in rows if r.get("state")})
    districts = sorted({str(r.get("district", "")).strip() for r in rows if r.get("district")})
    names = sorted({str(r.get("name", "")).strip() for r in rows if r.get("name")})
    state = states[0] if len(states) == 1 else (states[0] if states else None)
    return {
        "valid": True,
        "formatted": pin,
        "likely_state": state,
        "states": states,
        "districts": districts,
        "city": "",
        "locality": names[0] if names else "",
        "post_offices": names,
        "reason": f"Valid PIN, official India Post reference found ({len(rows)} post-office record(s))",
        "source": str(rows[0].get("source") or "India Post / data.gov.in"),
    }


def _invalid(digits, reason, error_type):
    return {
        "valid": False, "formatted": digits, "likely_state": None, "city": "", "locality": "",
        "reason": reason, "source": "format", "error_type": error_type, "reference_found": False,
    }


def validate_pin(pin: str) -> dict:
    """Validate an Indian PIN code.

    ``error_type`` separates a formatting problem ("missing", "format") from a
    reference result. ``reference_found`` is True only when a postal reference
    record exists for the PIN; a well-formed PIN that is absent from the
    available data is reported as unconfirmed, not as invalid.
    """
    digits = re.sub(r"\D", "", pin or "")
    if not digits:
        return _invalid("", "PIN code missing", "missing")
    if len(digits) != 6:
        return _invalid(digits, f"PIN format error: expected 6 digits, got {len(digits)}", "format")
    if digits[0] == "0":
        return _invalid(digits, "PIN format error: Indian PIN codes cannot start with 0", "format")
    if len(set(digits)) == 1:
        return _invalid(digits, "Repeated-digit PIN looks like a placeholder (e.g. 999999)", "format")

    try:
        official_rows = lookup_pincode(digits)
    except Exception:
        official_rows = []
    if official_rows:
        info = _official_to_pin_info(official_rows, digits)
        info.update({"error_type": None, "reference_found": True})
        return info

    exact = PIN_REFERENCE.get(digits)
    if exact:
        return {"valid": True, "formatted": digits, "likely_state": exact["state"], "city": exact.get("city", ""), "locality": exact.get("locality", ""), "reason": f"Valid PIN, exact project reference maps to {exact.get('city', '')}, {exact.get('state', '')}", "source": "project reference", "error_type": None, "reference_found": True}

    prefix2 = digits[:2]
    likely_state = PIN_PREFIX_TO_STATE.get(prefix2)
    if not likely_state:
        return {"valid": True, "formatted": digits, "likely_state": None, "city": "", "locality": "", "reason": "PIN format valid, but the PIN was not found in the available reference data", "source": "format", "error_type": None, "reference_found": False}
    return {"valid": True, "formatted": digits, "likely_state": likely_state, "city": "", "locality": "", "reason": f"PIN format valid; not found in postal reference data (prefix region suggests {likely_state})", "source": "project prefix reference", "error_type": None, "reference_found": False}
