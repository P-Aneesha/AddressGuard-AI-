from utils.indian_data import CITY_STATE_MAP, KNOWN_LOCALITIES
from services.official_reference_service import locality_matches

MIN_SUGGEST_CONFIDENCE = 60


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def resolve_and_rank(parsed: dict, corrections: list) -> list:
    """Rank correction suggestions using available geographic context.

    Generic text corrections (street/building/landmark/district) are retained
    instead of being discarded simply because they are not geographic fields.
    """
    ranked = []
    for correction in corrections or []:
        c = dict(correction)
        conf = int(c.get("confidence", 0) or 0)
        field = c.get("field", "")
        suggested = c.get("suggested", "")

        if field == "city":
            state_ctx = parsed.get("state", "")
            expected_state = CITY_STATE_MAP.get(suggested)
            if state_ctx and expected_state:
                if _norm(expected_state) == _norm(state_ctx):
                    conf = min(100, conf + 10)
                else:
                    conf = max(0, conf - 20)

        elif field == "locality":
            city_ctx = parsed.get("city", "")
            state_ctx = parsed.get("state", "")
            district_ctx = parsed.get("district", "")
            pin_ctx = parsed.get("pin_code", "")
            expected_city = KNOWN_LOCALITIES.get(suggested)
            if city_ctx and expected_city:
                if _norm(expected_city) == _norm(city_ctx):
                    conf = min(100, conf + 10)
                else:
                    conf = max(0, conf - 20)
            else:
                official = locality_matches(
                    suggested, city=city_ctx, district=district_ctx,
                    state=state_ctx, pin=pin_ctx,
                )
                if official.get("verified"):
                    conf = min(100, conf + 15)
                elif official.get("strong_candidate"):
                    conf = min(100, conf + 5)

        elif field == "state":
            city_ctx = parsed.get("city", "")
            expected_state = CITY_STATE_MAP.get(city_ctx, "")
            if city_ctx and expected_state:
                if _norm(expected_state) == _norm(suggested):
                    conf = min(100, conf + 10)
                else:
                    conf = max(0, conf - 20)

        c["confidence"] = conf
        if conf >= MIN_SUGGEST_CONFIDENCE:
            ranked.append(c)

    ranked.sort(key=lambda item: (-int(item.get("confidence", 0)), item.get("field", "")))
    return ranked
