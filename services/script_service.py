"""Addresses written in Indian scripts (Hindi, Telugu, Tamil, ...).

The rest of the pipeline and all reference data work in English, so an
address in another script is first rewritten in English by the configured
LLM. The original text is always kept. A machine translation is never
treated as verified: the decision stays at customer confirmation until a
person confirms the English version.
"""
import json
import logging

from utils.ai_cache import ResultCache

logger = logging.getLogger("addressguard.script")
_CACHE = ResultCache()

# Unicode blocks of the scheduled Indian scripts used in addresses.
SCRIPTS = {
    "Devanagari (Hindi/Marathi)": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF),
    "Gurmukhi (Punjabi)": (0x0A00, 0x0A7F), "Gujarati": (0x0A80, 0x0AFF), "Odia": (0x0B00, 0x0B7F),
    "Tamil": (0x0B80, 0x0BFF), "Telugu": (0x0C00, 0x0C7F), "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
}

TRANSLATE_PROMPT = """You rewrite an Indian delivery address from an Indian script into English (Latin script).
Rules:
- Transliterate names of people, buildings, streets, localities, cities and states into their standard English spelling (e.g. హైదరాబాద్ -> Hyderabad, तेलंगाना -> Telangana). Do not translate their meaning.
- Translate only generic address words (e.g. "फ्लैट" -> "Flat", "रोड" -> "Road", "पास" -> "Near").
- Keep every number, PIN code and phone number exactly.
- Keep the original order and separate parts with commas. Do not add, guess or correct anything.
Return ONLY a JSON object: {"address": "<the address in English>"}"""


def detect_script(text):
    """Return the Indian script that most letters are written in, or None for English."""
    counts = {}
    latin = 0
    for ch in str(text or ""):
        if ch.isascii():
            latin += ch.isalpha()
            continue
        code = ord(ch)
        for name, (low, high) in SCRIPTS.items():
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return None
    script, letters = max(counts.items(), key=lambda kv: kv[1])
    return script if letters >= latin else None


def normalize_digits(text):
    """Replace Indian-script digits (५, ౫, ௫ ...) with ASCII digits."""
    out = []
    for ch in str(text or ""):
        code = ord(ch)
        for low, high in SCRIPTS.values():
            # Each script's digits sit at offset 0x66-0x6F of its block.
            if low + 0x66 <= code <= low + 0x6F and code <= high:
                ch = str(code - low - 0x66)
                break
        out.append(ch)
    return "".join(out)


def translate_address(text, api_key, base_url, model, timeout):
    """Return (english_text, error). english_text is None when translation is unavailable."""
    if not api_key:
        return None, "the AI service is not configured"
    key = (model, base_url, text)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached, None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": TRANSLATE_PROMPT}, {"role": "user", "content": text}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        english = str(json.loads(response.choices[0].message.content).get("address") or "").strip()
    except Exception as exc:
        logger.warning("Address translation failed: %s", type(exc).__name__)
        return None, f"the AI service failed ({type(exc).__name__})"
    if not english or detect_script(english):
        return None, "the AI service did not return an English address"
    _CACHE.put(key, english)
    return english, None
