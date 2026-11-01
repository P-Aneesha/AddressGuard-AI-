import re

from utils.indian_data import BUILDING_KEYWORDS, FLAT_KEYWORDS, HOUSE_KEYWORDS, STREET_KEYWORDS

KEY_GEO_FIELDS = ["city", "state", "pin_code", "locality", "district"]
STRUCTURE_WORDS = [k for k in BUILDING_KEYWORDS + FLAT_KEYWORDS + HOUSE_KEYWORDS + STREET_KEYWORDS
                   if len(k) >= 3 and k != "st"] + ["house", "door", "floor", "near", "opp"]

def detect_anomalies(parsed: dict, raw_text: str) -> dict:
    reasons = []
    severity = "NONE"

    filled_geo = sum(1 for f in KEY_GEO_FIELDS if parsed.get(f))
    # A recipient name, phone, or PIN alone is not enough to establish that
    # meaningful address structure exists. This prevents random text from being
    # promoted into a valid-looking address simply because the parser found a name.
    has_any_structured_field = any(parsed.get(f) for f in
        ["house_number","flat_unit","building","street","landmark","locality","city","district","state"])
    leftover_ratio = 0
    total_words = len(raw_text.split()) or 1
    leftover_words = sum(len(t.split()) for t in parsed.get("unrecognized_text", []))
    leftover_ratio = leftover_words / total_words

    # The parser is generous ("lorem ipsum dolor" fuzzily reads as a door
    # number), so a filled field alone is not proof of an address. With no
    # geographic field, the raw text must also contain a real address word.
    keyword_evidence = any(
        re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", raw_text.lower())
        for k in STRUCTURE_WORDS
    )
    if not has_any_structured_field or (filled_geo == 0 and not keyword_evidence):
        reasons.append("No recognizable address components found")
        severity = "CRITICAL"
    elif filled_geo == 0:
        reasons.append("No city, state, PIN or locality could be identified")
        severity = "HIGH"

    if leftover_ratio > 0.6 and total_words >= 3:
        reasons.append("Majority of input is unrecognized / random text")
        severity = "HIGH" if severity in ("NONE", "MEDIUM") else severity

    pin = parsed.get("pin_code", "")
    if pin and len(set(pin)) == 1:
        reasons.append(f"PIN code {pin} is a repeated-digit placeholder pattern, not a real PIN")
        severity = "HIGH" if severity in ("NONE", "MEDIUM") else severity

    if re.search(r"(.)\1{5,}", raw_text.lower()):
        reasons.append("Raw text contains long repeated-character run")
        severity = "MEDIUM" if severity == "NONE" else severity

    alpha_tokens = re.findall(r"[a-zA-Z]{4,}", raw_text.lower())
    gibberish = sum(1 for t in alpha_tokens if not re.search(r"[aeiou]", t))
    if alpha_tokens and gibberish / len(alpha_tokens) > 0.4:
        reasons.append("Multiple vowel-less/gibberish tokens detected")
        severity = "HIGH" if severity in ("NONE", "MEDIUM") else severity

    return {
        "is_anomalous": severity != "NONE",
        "severity": severity,
        "reasons": reasons,
    }
