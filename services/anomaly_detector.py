import re

KEY_GEO_FIELDS = ["city", "state", "pin_code", "locality", "district"]

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

    if not has_any_structured_field:
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
        reasons.append(f"PIN code {pin} is a repeated-digit pattern, likely fake")
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
