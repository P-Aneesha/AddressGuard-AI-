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


def validate_pin(pin: str) -> dict:
    digits = re.sub(r"\D", "", pin or "")
    if not digits:
        return {"valid": False, "formatted": "", "likely_state": None, "city": "", "locality": "", "reason": "PIN code missing", "source": "format"}
    if len(digits) != 6:
        return {"valid": False, "formatted": digits, "likely_state": None, "city": "", "locality": "", "reason": f"Expected 6 digits, got {len(digits)}", "source": "format"}
    if len(set(digits)) == 1:
        return {"valid": False, "formatted": digits, "likely_state": None, "city": "", "locality": "", "reason": "Repeated-digit PIN looks invalid (e.g. 000000)", "source": "format"}

    official_rows = lookup_pincode(digits)
    if official_rows:
        return _official_to_pin_info(official_rows, digits)

    exact = PIN_REFERENCE.get(digits)
    if exact:
        return {"valid": True, "formatted": digits, "likely_state": exact["state"], "city": exact.get("city", ""), "locality": exact.get("locality", ""), "reason": f"Valid PIN, exact project reference maps to {exact.get('city', '')}, {exact.get('state', '')}", "source": "project reference"}

    prefix2 = digits[:2]
    likely_state = PIN_PREFIX_TO_STATE.get(prefix2)
    if not likely_state:
        return {"valid": True, "formatted": digits, "likely_state": None, "city": "", "locality": "", "reason": "PIN format valid; region unknown in available reference data", "source": "format"}
    return {"valid": True, "formatted": digits, "likely_state": likely_state, "city": "", "locality": "", "reason": f"Valid PIN, region maps to {likely_state}", "source": "project prefix reference"}
