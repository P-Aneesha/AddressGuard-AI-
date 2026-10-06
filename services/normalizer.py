import re
from utils.indian_data import ABBREVIATION_EXPANSIONS

def _titlecase(s):
    return " ".join(w.capitalize() if not w.isupper() or len(w) > 3 else w for w in s.split())

def _clean_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()

def _expand_abbrev(s):
    words = s.split()
    out = []
    for w in words:
        key = w.strip(".,").lower()
        out.append(ABBREVIATION_EXPANSIONS.get(key, w))
    return " ".join(out)

def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits

def normalize_pin(pin: str) -> str:
    return re.sub(r"\D", "", pin or "")

def normalize_address(parsed: dict) -> dict:
    """Safe normalization: whitespace, casing, abbreviation expansion, phone/pin format.
    Does NOT correct spelling of city/state/locality — that's the correction engine's job."""
    out = dict(parsed)
    for f in ["name","house_number","flat_unit","building","street","landmark","locality","city","district","state"]:
        if out.get(f):
            out[f] = _clean_ws(out[f])
    if out.get("name"):
        out["name"] = _titlecase(out["name"])
    if out.get("street"):
        out["street"] = _titlecase(_expand_abbrev(out["street"]))
    if out.get("landmark"):
        out["landmark"] = _titlecase(_expand_abbrev(out["landmark"]))
    if out.get("building"):
        out["building"] = _titlecase(out["building"])
    if out.get("locality"):
        out["locality"] = _titlecase(out["locality"])
    if out.get("city"):
        out["city"] = _titlecase(out["city"])
    if out.get("state"):
        out["state"] = _titlecase(out["state"])
    if out.get("house_number"):
        out["house_number"] = _expand_abbrev(out["house_number"])
    if out.get("flat_unit"):
        out["flat_unit"] = _expand_abbrev(out["flat_unit"])
    if out.get("phone"):
        out["phone"] = normalize_phone(out["phone"])
    if out.get("pin_code"):
        out["pin_code"] = normalize_pin(out["pin_code"])
    return out
