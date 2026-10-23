import json
import re
import difflib
import logging
from services.address_parser import parse_address, FIELDS
from utils.ai_cache import ResultCache

logger = logging.getLogger("addressguard.ai")
_CACHE = ResultCache()

RAW_ANCHOR_THRESHOLD = 0.55  # min fuzzy ratio to trust a segment as the "true" raw wording


def _sanitize(msg: str, api_key: str) -> str:
    """Never let a raw exception string leak the key (e.g. if it appears in a URL/header dump)."""
    msg = str(msg)
    if api_key and api_key in msg:
        msg = msg.replace(api_key, "***REDACTED***")
    return msg


def _anchor_to_raw_text(raw_text: str, parsed: dict) -> dict:
    """Groq sometimes 'helpfully' auto-corrects spelling during extraction despite the
    system prompt forbidding it (e.g. 'Karnatka' -> 'Karnataka'), which would silently
    hide typos from the correction engine. This re-anchors every text field back to the
    literal wording actually present in the raw input, so corrections are never bypassed."""
    segments = [s.strip(" .") for s in re.split(r"[,\n]", raw_text) if s.strip(" .")]
    out = dict(parsed)
    for field in ("name", "house_number", "flat_unit", "building", "street", "landmark",
                  "locality", "city", "district", "state"):
        value = out.get(field, "")
        if not value:
            continue
        if value.lower() in raw_text.lower():
            continue  # AI's wording is verbatim in the source text — trust it as-is
        best_seg, best_ratio = None, 0.0
        for seg in segments:
            ratio = difflib.SequenceMatcher(None, seg.lower(), value.lower()).ratio()
            if ratio > best_ratio:
                best_seg, best_ratio = seg, ratio
        if best_seg and best_ratio >= RAW_ANCHOR_THRESHOLD:
            out[field] = best_seg
    return out


SYSTEM_PROMPT = """You extract structured fields from a raw, unstructured Indian shipping address.
Return ONLY a JSON object with exactly these keys: name, phone, house_number, flat_unit, building, street, landmark, locality, city, district, state, pin_code.
Rules:
- Extract only what is explicitly present in the text, using the exact spelling/words as written. Do NOT correct spelling.
- Do NOT invent or guess missing values — use "" for anything absent.
- "Flat 302" / "Apt 5B" / "Unit 12" -> flat_unit, NOT house_number.
- "H.No 2-4-15" / "Door No 12" / "Plot 5" -> house_number.
- Apartment/society/building names (e.g. "Green Heights Apartments") -> building, NOT locality.
- Output raw JSON only. No markdown, no commentary."""

def extract_with_ai(raw_text: str, api_key: str, base_url: str, model: str, timeout: int) -> tuple:
    if not api_key:
        logger.warning("AI extraction skipped: GROQ_API_KEY is empty after config load.")
        parsed = parse_address(raw_text)
        return parsed, {"source": "fallback", "model": None, "status": "Fallback",
                         "error": "AI service not configured (GROQ_API_KEY is not set)"}
    cache_key = (model, base_url, raw_text)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": raw_text}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        parsed = {f: str(data.get(f, "") or "").strip() for f in FIELDS}
        parsed["unrecognized_text"] = []
        parsed = _anchor_to_raw_text(raw_text, parsed)
        result = (parsed, {"source": "ai", "model": model, "status": "Completed"})
        _CACHE.put(cache_key, result)
        return result
    except Exception as e:
        safe_err = _sanitize(f"{type(e).__name__}: {e}", api_key)
        logger.warning("Groq AI extraction failed, using deterministic fallback: %s", safe_err)
        parsed = parse_address(raw_text)
        # The full (sanitized) error stays in the server log; users see only its type.
        return parsed, {"source": "fallback", "model": None, "status": "Fallback", "error": f"AI service error: {type(e).__name__}"}
