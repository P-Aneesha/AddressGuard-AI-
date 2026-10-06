import re

def validate_phone(phone: str) -> dict:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not digits:
        return {"valid": False, "formatted": "", "reason": "Phone number missing"}
    if len(digits) != 10:
        return {"valid": False, "formatted": digits, "reason": f"Expected 10 digits, got {len(digits)}"}
    if digits[0] not in "6789":
        return {"valid": False, "formatted": digits, "reason": "Indian mobile numbers start with 6-9"}
    if len(set(digits)) == 1:
        return {"valid": False, "formatted": digits, "reason": "Repeated-digit number looks invalid"}
    return {"valid": True, "formatted": digits, "reason": "Valid 10-digit Indian mobile number"}
