import re
import difflib
from services.official_reference_service import reference_place_name
from utils.indian_data import (
    STATE_ALIASES, CITY_ALIASES, CITY_STATE_MAP, KNOWN_LOCALITIES, LOCALITY_ALIASES,
    STREET_KEYWORDS, HOUSE_KEYWORDS, FLAT_KEYWORDS, BUILDING_KEYWORDS,
)

# An optional short label (ph/mob/tel) is consumed with the number so it is not
# later misread as an address word, and "98100 12345" style spacing is accepted.
PHONE_RE = re.compile(
    r"(?:\b(?:ph|mob|tel|cell)\.?\s*[:#\-]?\s*)?(?:\+91[\-\s]?|\b0)?\b([6-9]\d{4}[\-\s]?\d{5})\b",
    re.I,
)
HOUSE_PREFIX_RE = re.compile(
    r"^(?:(?:h\.?\s*no|hno|house(?:\s+(?:no|number))?|door(?:\s+no)?|plot(?:\s+no)?)\.?)?\s*[:#-]?\s*"
    r"([0-9]+(?:[-/][0-9A-Za-z]+)*[A-Za-z]?)(.*)$",
    re.I,
)
ROAD_WORD_RE = re.compile(r"\b(?:road|rd|street|st|lane|ln|marg|salai|gali|cross|main|avenue|highway)\b", re.I)
# Unlabelled unit identifiers such as "B-12", "A/304", "C1".
ALNUM_UNIT_RE = re.compile(r"^[A-Za-z]{1,2}\s?[-/]?\s?\d{1,5}[A-Za-z]?$")
PIN_RE = re.compile(r"\b(\d{6})\b")
SPACED_PIN_RE = re.compile(r"\b[1-9]\d{2}\s\d{3}\b")
BAD_PIN_SEGMENT_RE = re.compile(r"(?:^|[,\n|])\s*(?:pin(?:code)?\s*[:#-]?\s*)?(\d{4,5}|\d{7})\s*(?=$|[,\n|])", re.I)

FIELDS = [
    "name", "phone", "house_number", "flat_unit", "building", "street", "landmark",
    "locality", "city", "district", "state", "pin_code"
]

# Courier / invoice / WhatsApp labels are metadata, not address content.
LABEL_RE = re.compile(
    r"\b(?:deliver\s*to|ship\s*to|shipping\s*address|delivery\s*address|"
    r"address|customer|recipient|name|mobile|phone|contact|pin(?:code)?|"
    r"postal\s*code|pincode|landmark|pls|please|kindly)\s*[:#\-]?\s*",
    re.I,
)


def _empty():
    d = {f: "" for f in FIELDS}
    d["unrecognized_text"] = []
    d["_raw_correction_fields"] = {}
    return d


def _has_kw(text, kws):
    t = text.lower().strip()
    if any(
        re.search(r"(?<![a-z0-9])" + re.escape(str(k).lower().strip()) + r"(?![a-z0-9])", t)
        for k in kws if str(k).strip()
    ):
        return True

    # Tolerate obvious spelling errors in structural keywords so a value such
    # as "Lake View Apartmnts" is still classified as a building rather than
    # being discarded as unrecognized text. Keep the threshold conservative to
    # avoid turning ordinary names into structural fields.
    tokens = re.findall(r"[a-z]+", t)
    for token in tokens:
        if len(token) < 4:
            continue
        for keyword in kws:
            keyword = str(keyword or "").strip().lower()
            if len(keyword) < 4:
                continue
            if difflib.SequenceMatcher(None, token, keyword).ratio() >= 0.84:
                return True
    return False


def _clean_token(text):
    parts = str(text or "").split()
    return re.sub(r"[^A-Za-z]", "", parts[0]) if parts else ""


def _looks_like_landmark(text):
    first = _clean_token(text).lower()
    if not first:
        return False
    words = (
        "near", "neer", "opp", "opposit", "opposite",
        "beside", "besid", "behind", "next", "adjacent",
    )
    return first in words or any(
        difflib.SequenceMatcher(None, first, w).ratio() >= 0.82
        for w in words
    )


def _match_alias(text, alias_map):
    t = text.lower().strip()
    if t in alias_map:
        return alias_map[t]
    return None


def _canonical_from_text(text, mapping):
    """Find the longest known reference value/alias embedded in a segment."""
    low = str(text or "").lower()
    candidates = []
    for alias, canonical in mapping.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])", low):
            candidates.append((len(alias), canonical, alias))
    for canonical in mapping.keys():
        if re.search(r"(?<![a-z0-9])" + re.escape(str(canonical).lower()) + r"(?![a-z0-9])", low):
            candidates.append((len(str(canonical)), canonical, canonical))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])


def _remove_phrase(text, phrase):
    if not phrase:
        return text
    return re.sub(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", " ", text, flags=re.I)


def _strip_labels(text):
    return LABEL_RE.sub(" ", text or "")


def _clean_segment(text):
    text = _strip_labels(text)
    text = re.sub(r"^[\s:;,.\-]+|[\s:;,.\-]+$", "", text)
    return re.sub(r"\s+", " ", text).strip()


UNIT_RE = re.compile(
    r"(\b(?:flat|apt|unit|suite|h\.?\s*no|hno|house\s+no|door\s+no|plot\s+no|plot)\.?\s*[:#-]?\s*\d[0-9A-Za-z/-]*)\s+",
    re.I,
)
ROAD_END_RE = re.compile(r"(\b(?:road|rd|street|lane|marg|salai|avenue|highway)\b\.?)\s+", re.I)


def _split_unpunctuated(text):
    """Insert segment breaks into an address typed without commas or newlines.

    "ravi flat 12 lotus towers mg road indiranagar" becomes
    "ravi, flat 12, lotus towers, mg road, indiranagar" so the normal
    segment-based parsing can classify each part.
    """
    if re.search(r"[\n,|]", text) or len(text.split()) < 6:
        return text
    text = re.sub(r"\s+(?=(?:flat|apt|unit|suite|h\.?\s*no|hno|house\s+no|door\s+no|plot\s+no)\b)", ", ", text, flags=re.I)
    text = UNIT_RE.sub(r"\1, ", text)
    building_end = r"(\b(?:" + "|".join(re.escape(k) for k in BUILDING_KEYWORDS) + r")\b)\s+"
    text = re.sub(building_end, r"\1, ", text, flags=re.I)
    return ROAD_END_RE.sub(r"\1, ", text)


def _append(result, field, value, separator="; "):
    value = _clean_segment(value)
    if not value:
        return
    result[field] = (result[field] + separator + value).strip(separator) if result[field] else value


def parse_address(raw: str) -> dict:
    """Order-independent deterministic address parser.

    It detects high-signal components first (phone, PIN, state, city, locality,
    house/flat/building/street/landmark), then assigns remaining text. It does
    not depend on fixed line positions and recognizes harmless courier labels.
    """
    result = _empty()
    text = str(raw or "").strip()
    if not text:
        return result

    # Normalize separators commonly used in courier labels, invoices and copied
    # WhatsApp addresses. Newlines remain meaningful only as segment boundaries.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Some WhatsApp messages lose line breaks when copied. Split explicit
    # metadata labels back into logical segments so `Name: ... H.No: ...` is
    # still parsed field-by-field instead of being swallowed as one street.
    text = re.sub(
        r"(?i)(?<!^)\s+(?=(?:name|customer|recipient|mobile|phone|contact|h\.?\s*no|house(?:\s+number)?|flat|apt|unit|address|landmark|pin(?:code)?|postal\s*code)\s*[:#])",
        "\n",
        text,
    )

    # Detect phone/PIN globally before field classification, regardless of order.
    m = PHONE_RE.search(text)
    if m:
        result["phone"] = re.sub(r"\D", "", m.group(1))
        text = text[:m.start()] + " " + text[m.end():]

    pm = PIN_RE.search(text) or SPACED_PIN_RE.search(text)
    if pm:
        result["pin_code"] = re.sub(r"\D", "", pm.group(0))
        text = text[:pm.start()] + " " + text[pm.end():]
    else:
        # A standalone wrong-length number in its own segment is almost always a
        # mistyped PIN. Keep it so validation reports a format error instead of
        # claiming that no PIN was supplied.
        bad = BAD_PIN_SEGMENT_RE.search(text)
        if bad:
            result["pin_code"] = bad.group(1)
            text = text[:bad.start(1)] + " " + text[bad.end(1):]

    text = _split_unpunctuated(text)

    # Split all ordinary address presentation formats.
    segments = [
        _clean_segment(s)
        for s in re.split(r"[\n,|]+", text)
        if _clean_segment(s)
    ]

    # First pass: extract known geographic components even when they share a line.
    residual_segments = []
    street_candidates = []
    weak_locality = False
    partial_locality_segment = ""
    for seg in segments:
        work = seg

        state_hit = _canonical_from_text(work, STATE_ALIASES)
        if state_hit:
            _, _, matched = state_hit
            result["state"] = state_hit[1]
            matched_text = str(matched).strip()
            # "New Delhi" is both a city name and a common way of naming the
            # Delhi state/UT. Preserve the city before removing the state phrase.
            if matched_text.lower() == "new delhi" and not result["city"]:
                result["city"] = "New Delhi"
            # Treat "New Delhi" as a valid state alias in this context rather
            # than showing a misleading spelling correction for "Delhi".
            if matched_text.lower() != "new delhi" and not re.fullmatch(r"(?i)" + re.escape(str(state_hit[1])), matched_text):
                result["_raw_correction_fields"]["state"] = matched_text
            work = _remove_phrase(work, matched)
            # A segment may contain both city and state (e.g. Bengaluru Karnataka).

        city_hit = _canonical_from_text(work, CITY_ALIASES)
        if not city_hit:
            # CITY_STATE_MAP is canonical city -> state, so build a temporary alias map.
            city_alias_map = {c: c for c in CITY_STATE_MAP}
            city_hit = _canonical_from_text(work, city_alias_map)
        if city_hit:
            _, _, matched = city_hit
            # "Kollam, Kollam": a city name repeated in a later segment means the
            # earlier occurrence was the locality (a post office of that name).
            if result["city"] == city_hit[1] and not result["locality"] and not _remove_phrase(work, matched).strip():
                result["locality"] = city_hit[1]
            result["city"] = city_hit[1]
            if not re.fullmatch(r"(?i)" + re.escape(str(city_hit[1])), str(matched).strip()):
                result["_raw_correction_fields"]["city"] = str(matched).strip()
            work = _remove_phrase(work, matched)

        locality_map = dict(LOCALITY_ALIASES)
        locality_map.update({k: k for k in KNOWN_LOCALITIES})
        loc_hit = _canonical_from_text(work, locality_map)
        if loc_hit and _looks_like_landmark(work):
            # "Near Andheri Station" is a landmark: keep it intact and only use
            # the embedded place as a locality hint when nothing better exists.
            if not result["locality"]:
                result["locality"] = loc_hit[1]
        elif loc_hit:
            _, _, matched = loc_hit
            result["locality"] = loc_hit[1]
            if not re.fullmatch(r"(?i)" + re.escape(str(loc_hit[1])), str(matched).strip()):
                result["_raw_correction_fields"]["locality"] = str(matched).strip()
            # Preserve a complete building name when the locality is embedded
            # in it, e.g. "Green Park Residency".
            remaining_after_locality = _remove_phrase(work, matched)
            if remaining_after_locality.strip() and _has_kw(remaining_after_locality, BUILDING_KEYWORDS):
                result["building"] = _clean_segment(work)
                result["_raw_correction_fields"]["building"] = result["building"]
                # Only a hint: a real locality elsewhere in the address wins.
                weak_locality = True
                work = ""
            else:
                if remaining_after_locality.strip():
                    # "C T T Nagar" contains the known "T Nagar"; the whole
                    # segment may be the real place name.
                    partial_locality_segment = _clean_segment(work)
                work = remaining_after_locality

        residual = _clean_segment(work)
        if residual:
            # High-signal structural phrase: keep road/street segments for the
            # structural pass instead of allowing fuzzy geography to consume them.
            if _has_kw(residual, STREET_KEYWORDS) and not _looks_like_landmark(residual):
                # "house 45 sector 21": split the house identifier off the street.
                house_match = HOUSE_PREFIX_RE.match(residual)
                if (house_match and not result["house_number"]
                        and re.match(r"[\s:,.\-]+[A-Za-z]", house_match.group(2))):
                    result["house_number"] = house_match.group(1).strip()
                    residual = _clean_segment(house_match.group(2))
                # Keep every street-like segment instead of overwriting: one of
                # them may turn out to be the locality (e.g. "Lajpat Nagar").
                street_candidates.append(residual)
                result["street"] = street_candidates[0]
                result["_raw_correction_fields"]["street"] = street_candidates[0]
                continue
            residual_segments.append(residual)

    # Fuzzy geographic pass: tolerate previously unseen misspellings while
    # keeping structural phrases out of geographic fields. This is deliberately
    # generic and uses the existing reference data rather than test-case rules.
    def _fuzzy_reference(value, candidates, threshold):
        value = re.sub(r"[^a-z ]", "", value.lower()).strip()
        if not value or len(value.split()) > 4:
            return None
        best = None
        for candidate in candidates:
            ratio = difflib.SequenceMatcher(None, value, candidate.lower()).ratio()
            if ratio >= threshold and (best is None or ratio > best[0]):
                best = (ratio, candidate)
        return best[1] if best else None

    remaining_for_structure = []
    for seg in residual_segments:
        low = seg.lower()
        if not result["state"]:
            candidate = _fuzzy_reference(seg, STATE_ALIASES.values(), 0.80)
            if candidate and not _has_kw(low, HOUSE_KEYWORDS + STREET_KEYWORDS + BUILDING_KEYWORDS):
                result["state"] = candidate
                result["_raw_correction_fields"]["state"] = seg
                continue
        if not result["city"]:
            # Prefer cities of the stated state: "Knapur, Uttar Pradesh" is Kanpur, not Nagpur.
            # Once the state is known, a city of another state is a contradiction, not a correction.
            state_cities = [c for c, s in CITY_STATE_MAP.items() if s == result["state"]]
            candidate = _fuzzy_reference(seg, state_cities, 0.70) if state_cities \
                else _fuzzy_reference(seg, CITY_STATE_MAP.keys(), 0.78)
            if candidate and not _has_kw(low, HOUSE_KEYWORDS + STREET_KEYWORDS + BUILDING_KEYWORDS):
                result["city"] = candidate
                result["_raw_correction_fields"]["city"] = seg
                continue
        if not result["locality"]:
            candidate = _fuzzy_reference(seg, KNOWN_LOCALITIES.keys(), 0.80)
            if candidate and not _has_kw(low, HOUSE_KEYWORDS + STREET_KEYWORDS + BUILDING_KEYWORDS):
                result["locality"] = candidate
                result["_raw_correction_fields"]["locality"] = seg
                continue
        remaining_for_structure.append(seg)

    residual_segments = remaining_for_structure

    # Second pass: structural fields and harmless metadata labels.
    name_found = False
    for seg in residual_segments:
        low = seg.lower()
        if not seg:
            continue

        # Explicit field labels can be embedded in the same segment.
        if _has_kw(low, FLAT_KEYWORDS):
            _append(result, "flat_unit", seg, " ")
            continue
        if _has_kw(low, HOUSE_KEYWORDS + ["house", "door"]):
            # Preserve a street tail when a copied WhatsApp label contains both
            # the house identifier and road text: `H.No: 8-2-293 Road No 5`.
            house_match = HOUSE_PREFIX_RE.match(seg)
            if house_match and house_match.group(2).strip() and _has_kw(house_match.group(2), STREET_KEYWORDS):
                result["house_number"] = house_match.group(1).strip()
                _append(result, "street", house_match.group(2), " ")
                result["_raw_correction_fields"]["street"] = result["street"]
            else:
                _append(result, "house_number", seg, " ")
            continue
        if _has_kw(low, BUILDING_KEYWORDS):
            _append(result, "building", seg)
            result["_raw_correction_fields"]["building"] = result["building"]
            continue
        if _has_kw(low, STREET_KEYWORDS):
            # A house-labelled segment was already consumed above. Therefore
            # 'House 12' is not incorrectly turned into a street.
            _append(result, "street", seg)
            result["_raw_correction_fields"]["street"] = result["street"]
            continue
        if _looks_like_landmark(seg):
            _append(result, "landmark", seg)
            result["_raw_correction_fields"]["landmark"] = result["landmark"]
            continue

        # Explicit district label.
        if re.search(r"\bdistrict\b", low):
            _append(result, "district", seg)
            result["_raw_correction_fields"]["district"] = result["district"]
            continue

        # Explicit street-number phrases must be treated as streets, not house numbers.
        # Examples: Road No 10, Road No. 12, Rd No 5, 2nd Cross Road, 5th Main Road.
        if re.match(r"^(?:road|rd)\s*(?:no\.?\s*)?\d+[A-Za-z]?(?:\s+(?:road|street))?$", low):
            result["street"] = seg
            result["_raw_correction_fields"]["street"] = seg
            continue
        if re.search(r"\b(?:\d+(?:st|nd|rd|th)\s+(?:main|cross)|(?:main|cross)\s+road)\b", low):
            result["street"] = seg
            result["_raw_correction_fields"]["street"] = seg
            continue

        # Plain house/flat patterns without labels.
        if re.match(r"^(?:\d+[A-Za-z]?[-/]?\d*[A-Za-z]?|\d+[-/]\d+[-/]\d+)(?:\s|$)", seg) or ALNUM_UNIT_RE.match(seg):
            if not result["house_number"]:
                result["house_number"] = seg
                continue

        # The first short alphabetic segment is generally the recipient/name.
        if not name_found and re.fullmatch(r"[A-Za-z.\s]+", seg) and 1 <= len(seg.split()) <= 4:
            result["name"] = seg
            name_found = True
            continue

        # Remaining text that looks like a normal locality/building/street phrase
        # is retained for downstream correction rather than silently discarded.
        # Markup/code characters never occur in a street name, so such text is
        # left unrecognised instead of being promoted to a street.
        if re.search(r"\d", seg) and not result["street"] and not re.search(r"[<>{}=]", seg):
            result["street"] = seg
            continue

        result["unrecognized_text"].append(seg)

    # Final structural safety pass: if a segment unmistakably contains a road/street
    # keyword, preserve it even when an earlier geographic pass consumed part of it.
    if not result["street"]:
        for seg in segments:
            if _has_kw(seg, STREET_KEYWORDS) and not _looks_like_landmark(seg):
                result["street"] = seg
                result["_raw_correction_fields"]["street"] = seg
                break

    # Locality from the whole-India reference data: when the built-in list did
    # not identify a locality, a leftover street-like or unrecognised segment
    # that exactly matches a post office, OSM locality or LGD village in the
    # stated state is taken as the locality.
    if partial_locality_segment and reference_place_name(partial_locality_segment, result["state"]):
        result["locality"] = partial_locality_segment
        result["_raw_correction_fields"].pop("locality", None)
        result["unrecognized_text"] = [
            t for t in result["unrecognized_text"] if t.lower() not in partial_locality_segment.lower()
        ]
    if not result["locality"] or weak_locality:
        if weak_locality:
            result["_raw_correction_fields"].pop("locality", None)
        pool = list(result["unrecognized_text"]) + street_candidates[1:] + street_candidates[:1]
        for candidate in pool:
            # Road names often double as post-office names ("Station Road"), so
            # a segment that names a road is never taken as the locality.
            if ROAD_WORD_RE.search(candidate):
                continue
            if reference_place_name(candidate, result["state"]):
                result["locality"] = candidate
                if candidate in result["unrecognized_text"]:
                    result["unrecognized_text"].remove(candidate)
                if candidate in street_candidates:
                    street_candidates.remove(candidate)
                    result["street"] = street_candidates[0] if street_candidates else ""
                    if result["street"]:
                        result["_raw_correction_fields"]["street"] = result["street"]
                    else:
                        result["_raw_correction_fields"].pop("street", None)
                break

    # If state extraction left a harmless metadata word such as Mobile, do not
    # treat it as geographic data or a problem.
    result["state"] = _clean_segment(result["state"])
    result["city"] = _clean_segment(result["city"])
    # Delhi and Chandigarh are both the state/UT and the city: "Sarojini Nagar,
    # Delhi" names the city even though the parser read "Delhi" as the state.
    if not result["city"] and result["state"] in CITY_STATE_MAP:
        result["city"] = result["state"]
    result["locality"] = _clean_segment(result["locality"])

    return result
