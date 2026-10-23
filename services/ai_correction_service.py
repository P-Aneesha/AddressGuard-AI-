"""Context-aware AI spelling correction for AddressGuard.

The AI is used to identify likely spelling errors in the COMPLETE address,
not to maintain a list of hard-coded misspelling -> correction pairs.
Corrections are suggestions only. The user must accept them before they are
applied to the address.
"""
import json
import logging
import re

from utils.ai_cache import ResultCache

logger = logging.getLogger("addressguard.ai_correction")
_CACHE = ResultCache()

MIN_CONFIDENCE = 70

SYSTEM_PROMPT = r"""
You are AddressGuard's context-aware Indian address spelling correction engine.

Your ONLY job is to detect likely SPELLING/TYPING errors in an address and
suggest the most likely intended spelling by considering the COMPLETE address.
You are NOT a general address generator and you must not invent missing data.

Return ONLY valid JSON in exactly this shape:
{
  "corrections": [
    {
      "field": "city|state|district|locality|street|building|landmark|name|other",
      "original": "exact text from the input",
      "suggested": "corrected spelling",
      "confidence": 0,
      "reason": "short explanation"
    }
  ]
}

Rules:
1. Correct spelling/typing mistakes even when the exact mistake has never been
   seen before. Use language knowledge and the surrounding address context.
2. Analyze the COMPLETE address together. Do not judge a word only in isolation.
3. Preserve all house numbers, flat numbers, PIN codes, phone numbers and other
   numeric identifiers exactly. Never alter numbers as a spelling correction.
4. Do not invent a building, locality, street, city or landmark that is not
   reasonably supported by the supplied text/context.
5. Do not silently apply corrections. Only return suggestions.
6. If a word is a valid-looking proper name and there is not enough evidence for
   a spelling correction, return no correction for it.
7. If multiple corrections are present, return all independent corrections.
8. Keep `original` exactly as it appears in the supplied address when practical.
9. Confidence is 0-100 and represents confidence that the spelling itself is
   wrong AND that the suggested spelling is the intended one.
10. Prefer no suggestion over a speculative suggestion.
11. Do not rewrite the address style or reorder fields. Only correct likely
    spelling/typing errors.
12. Do not return markdown, comments, or any text outside the JSON object.
"""


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _safe_json(content):
    """Parse strict JSON, tolerating accidental fenced JSON from a model."""
    content = str(content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def generate_ai_corrections(raw_text, parsed, api_key, base_url, model, timeout):
    """Return explainable contextual spelling suggestions from the configured LLM."""
    if not api_key:
        return [], {"source": "fallback", "status": "Unavailable", "error": "GROQ_API_KEY not configured"}

    context = {
        "raw_address": raw_text,
        "parsed_fields": {
            key: value for key, value in (parsed or {}).items()
            if key != "unrecognized_text" and value
        },
    }

    cache_key = (model, base_url, json.dumps(context, ensure_ascii=False, sort_keys=True))
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = _safe_json(response.choices[0].message.content)
        items = data.get("corrections", [])
        if not isinstance(items, list):
            items = []

        corrections = []
        for item in items:
            if not isinstance(item, dict):
                continue
            original = _clean(item.get("original"))
            suggested = _clean(item.get("suggested"))
            field = _clean(item.get("field")).lower() or "other"
            if field not in {"city", "state", "district", "locality", "street", "building", "landmark", "name", "other", "unrecognized_text"}:
                field = "other"
            if field == "other":
                field = "unrecognized_text"
            reason = _clean(item.get("reason")) or "Context-aware spelling correction"
            try:
                confidence = max(0, min(100, int(float(item.get("confidence", 0)))))
            except (TypeError, ValueError):
                confidence = 0

            if not original or not suggested or original.lower() == suggested.lower():
                continue
            if confidence < MIN_CONFIDENCE:
                continue
            if re.search(r"\d", original) or re.search(r"\d", suggested):
                # AI spelling correction must never rewrite numeric identifiers.
                continue

            corrections.append({
                "field": field,
                "original": original,
                "suggested": suggested,
                "reason": f"AI contextual correction — {reason}",
                "confidence": confidence,
                "method": "AI contextual spelling correction",
            })

        result = (corrections, {"source": "ai", "status": "Completed", "model": model})
        _CACHE.put(cache_key, result)
        return result

    except Exception as exc:
        logger.warning("AI spelling correction failed: %s", exc)
        return [], {
            "source": "fallback",
            "status": "Fallback",
            "model": model,
            "error": type(exc).__name__,
        }
