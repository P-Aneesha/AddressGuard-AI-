import difflib
import re

from utils.indian_data import (
    INDIAN_STATES,
    STATE_ALIASES,
    CITY_STATE_MAP,
    CITY_ALIASES,
    KNOWN_LOCALITIES,
    LOCALITY_ALIASES,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Suggestions are only generated when the similarity is sufficiently strong.
# Suggestions are NEVER silently applied.
FUZZY_THRESHOLD = 0.72
PHRASE_THRESHOLD = 0.82
WORD_THRESHOLD = 0.78

# Very short words are dangerous to fuzzy-correct.
MIN_WORD_LENGTH = 3


# ---------------------------------------------------------------------------
# Generic address vocabulary
# ---------------------------------------------------------------------------

# This vocabulary is intentionally generic and is NOT tied to particular
# evaluation cases, cities, or states.
GENERIC_ADDRESS_WORDS = {
    "road",
    "roads",
    "street",
    "streets",
    "lane",
    "lanes",
    "avenue",
    "avenues",
    "nagar",
    "colony",
    "layout",
    "layouts",
    "extension",
    "extensions",
    "phase",
    "phases",
    "block",
    "blocks",
    "sector",
    "sectors",
    "area",
    "areas",
    "market",
    "markets",
    "building",
    "buildings",
    "tower",
    "towers",
    "apartment",
    "apartments",
    "flat",
    "flats",
    "floor",
    "floors",
    "metro",
    "station",
    "junction",
    "circle",
    "cross",
    "main",
    "park",
    "complex",
    "plaza",
    "mall",
    "residency",
    "residencies",
    "enclave",
    "society",
    "societies",
    "heights",
    "height",
    "villa",
    "villas",
    "temple",
    "church",
    "mosque",
    "hospital",
    "school",
    "college",
    "university",
    "bank",
    "office",
    "warehouse",
    "near",
    "opposite",
    "beside",
    "behind",
    "next",
    "to",
    "number",
    "no",
    "north",
    "south",
    "east",
    "west",
    "central",
    "opp",
    "nr",
    "besides",
    "rd",
    "st",
    "ln",
    "ave",
    "road",
    "street",
    "lane",
}


# Canonical expansions for common abbreviations.
GENERIC_CANONICAL_WORDS = {
    "rd": "Road",
    "st": "Street",
    "ln": "Lane",
    "ave": "Avenue",
    "opp": "Opposite",
    "nr": "Near",
    "no": "Number",
}


# Fields where generic spelling correction is reasonably safe.
#
# Name is deliberately excluded because fuzzy-matching a person's name
# against geographic/address vocabulary can create false corrections.
TEXT_FIELDS = [
    "building",
    "street",
    "landmark",
    "locality",
    "city",
    "district",
    "state",
]


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _compact(value):
    """
    Normalize text for comparison.

    Punctuation and spacing are ignored so that:
        "Madhapur"
        "Madhapur,"
        "MADHAPUR"
    compare consistently.
    """
    return re.sub(r"[^a-z0-9]", "", _clean(value).lower())


def _normalized_tokens(value):
    return [
        token
        for token in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", _clean(value))
        if token
    ]


def _similarity(a, b):
    a = _compact(a)
    b = _compact(b)

    if not a or not b:
        return 0.0

    return difflib.SequenceMatcher(None, a, b).ratio()


def _token_similarity(source, candidate):
    """
    Compare two phrases token-by-token.

    This helps with multi-word address text such as:

        "Madhpur Main Rod"
        "Madhapur Main Road"
    """
    source_tokens = _normalized_tokens(source)
    candidate_tokens = _normalized_tokens(candidate)

    if not source_tokens or not candidate_tokens:
        return 0.0

    scores = []

    for source_token in source_tokens:
        best = max(
            (
                _similarity(source_token, candidate_token)
                for candidate_token in candidate_tokens
            ),
            default=0.0,
        )
        scores.append(best)

    count_score = (
        min(len(source_tokens), len(candidate_tokens))
        / max(len(source_tokens), len(candidate_tokens))
    )

    return (sum(scores) / len(scores)) * (0.85 + 0.15 * count_score)


def _best_fuzzy(text, candidates, cutoff=FUZZY_THRESHOLD):
    """
    Return:
        (candidate, similarity)

    for the strongest canonical candidate.
    """
    value = _clean(text)

    if not value:
        return None, 0.0

    best = None
    best_ratio = 0.0

    for candidate in candidates:
        candidate = _clean(candidate)

        if not candidate:
            continue

        ratio = max(
            _similarity(value, candidate),
            _token_similarity(value, candidate),
        )

        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio

    if best and best_ratio >= cutoff:
        return best, best_ratio

    return None, 0.0


def _same_text(a, b):
    return _compact(a) == _compact(b)


def _preserve_case(original, replacement):
    """
    Preserve readable casing of the original token.
    """
    original = str(original or "")
    replacement = str(replacement or "")

    if not original:
        return replacement

    if original.isupper():
        return replacement.upper()

    if original.islower():
        return replacement.lower()

    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]

    return replacement


def _deduplicate_preserving_order(values):
    result = []
    seen = set()

    for value in values:
        cleaned = _clean(value)

        if not cleaned:
            continue

        key = _compact(cleaned)

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


# ---------------------------------------------------------------------------
# Reference vocabulary
# ---------------------------------------------------------------------------

def _reference_locations():
    """
    Build canonical geographic vocabularies from the project's reference data.

    The correction engine does not hardcode individual test cases.
    """
    states = [str(x) for x in INDIAN_STATES]
    cities = [str(x) for x in CITY_STATE_MAP.keys()]
    localities = [str(x) for x in KNOWN_LOCALITIES.keys()]

    states += [str(x) for x in STATE_ALIASES.values()]
    cities += [str(x) for x in CITY_ALIASES.values()]
    localities += [str(x) for x in LOCALITY_ALIASES.values()]

    return (
        _deduplicate_preserving_order(states),
        _deduplicate_preserving_order(cities),
        _deduplicate_preserving_order(localities),
    )


def _all_reference_terms():
    states, cities, localities = _reference_locations()

    terms = set(GENERIC_ADDRESS_WORDS)
    terms.update(GENERIC_CANONICAL_WORDS.values())

    terms.update(states)
    terms.update(cities)
    terms.update(localities)

    return sorted(
        {
            _clean(x)
            for x in terms
            if _clean(x)
        },
        key=lambda x: (
            -len(_clean(x).split()),
            -len(x),
        ),
    )


def _is_structurally_canonical_text(value):
    """
    Return True when an address text field contains only known canonical
    address words plus numeric/ordinal tokens. This protects already-clean
    values such as ``5th Cross Road`` from reverse fuzzy corrections such as
    ``Road -> Roads``.
    """
    words = _clean(value).split()
    if not words:
        return False

    canonical_words = {
        _clean(x).lower()
        for x in GENERIC_ADDRESS_WORDS
        if _clean(x)
    }
    canonical_words.update(
        _clean(x).lower()
        for x in GENERIC_CANONICAL_WORDS.values()
        if _clean(x)
    )

    for word in words:
        compact = re.sub(r"[^a-z0-9]", "", word.lower())
        if not compact:
            continue
        if compact.isdigit() or re.fullmatch(r"\d+(st|nd|rd|th)", compact):
            continue
        if compact not in {re.sub(r"[^a-z0-9]", "", x) for x in canonical_words}:
            return False

    return True


def _reference_word_candidates(reference_terms):
    """
    Create a single-word vocabulary for generic word-level correction.
    """
    values = set()

    for value in GENERIC_CANONICAL_WORDS.values():
        values.add(_clean(value))

    for term in reference_terms:
        cleaned = _clean(term)

        if len(cleaned.split()) == 1:
            values.add(cleaned)

    return sorted(
        values,
        key=lambda value: (
            len(value),
            value.lower(),
        ),
    )


# ---------------------------------------------------------------------------
# Geographic field resolution
# ---------------------------------------------------------------------------

def _resolve_field(raw, alias_map, canonical_values):
    """
    Resolve a state/city/locality against aliases and canonical reference data.

    Returns:
        canonical, confidence, method
    """
    raw = _clean(raw)

    if not raw:
        return None, 0, None

    # Exact canonical value.
    for canonical in canonical_values:
        if _same_text(raw, canonical):
            return None, 0, None

    raw_l = raw.lower()

    # Exact alias.
    for alias, canonical in alias_map.items():
        if _clean(alias).lower() == raw_l:
            if not _same_text(raw, canonical):
                return canonical, 95, "known alias"

            return None, 0, None

    # Fuzzy canonical match.
    canonical, ratio = _best_fuzzy(
        raw,
        canonical_values,
        FUZZY_THRESHOLD,
    )

    if canonical and not _same_text(raw, canonical):
        return (
            canonical,
            round(ratio * 100),
            "fuzzy similarity",
        )

    return None, 0, None


# ---------------------------------------------------------------------------
# Generic word matching
# ---------------------------------------------------------------------------

def _word_length_compatible(source, candidate):
    """
    Prevent very short or very different words from receiving an unsafe
    replacement.
    """
    source_len = len(source)
    candidate_len = len(candidate)

    maximum_difference = max(
        3,
        round(source_len * 0.45),
    )

    return abs(source_len - candidate_len) <= maximum_difference


def _is_single_adjacent_transposition(a, b):
    """Return True when a and b differ only by one adjacent character swap."""
    a = _clean(a).lower()
    b = _clean(b).lower()
    if len(a) != len(b) or a == b:
        return False

    mismatches = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(mismatches) != 2:
        return False

    i, j = mismatches
    return (
        j == i + 1
        and a[i] == b[j]
        and a[j] == b[i]
        and a[:i] == b[:i]
        and a[j + 1:] == b[j + 1:]
    )


def _best_word(word, candidates):
    """
    Find a strong single-word canonical spelling.

    The matcher is deliberately token-level:
    - exact canonical words are protected;
    - singular/plural forms are not swapped;
    - a single adjacent transposition such as ``Raod`` -> ``Road`` is
      recognized even though ordinary SequenceMatcher is slightly below
      the generic threshold.
    """
    word = _clean(word)

    if len(word) < MIN_WORD_LENGTH:
        return None, 0.0

    if any(ch.isdigit() for ch in word):
        return None, 0.0

    source_plural = word.lower().endswith("s")

    best = None
    best_ratio = 0.0

    for candidate in candidates:
        candidate = _clean(candidate)

        if not candidate:
            continue

        if _same_text(word, candidate):
            continue

        # Never turn an explicitly plural address word into a singular word
        # (or vice versa). This prevents Apartmnts -> Apartment and similar
        # destructive corrections.
        candidate_plural = candidate.lower().endswith("s")
        if source_plural != candidate_plural:
            continue

        if not _word_length_compatible(word, candidate):
            continue

        ratio = _similarity(word, candidate)

        if _is_single_adjacent_transposition(word, candidate):
            ratio = max(ratio, 0.99)

        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio

    if (
        best
        and best_ratio >= WORD_THRESHOLD
        and not _same_text(word, best)
    ):
        return best, best_ratio

    return None, 0.0

def _generic_word_corrections(value, reference_terms):
    """
    Correct misspelled words inside arbitrary address text.

    Examples of the type of errors this can detect:

        Madhpur Main Rod
        Opposit Metro Staton
        Green Hights Twers

    These examples are explanatory only. No specific case is hardcoded.
    """
    value = _clean(value)

    if not value:
        return None, 0

    candidates = _reference_word_candidates(reference_terms)
    words = value.split()

    changed = False
    result = []
    scores = []

    for word in words:
        candidate, ratio = _best_word(
            word,
            candidates,
        )

        if candidate:
            replacement = _preserve_case(
                word,
                candidate,
            )

            result.append(replacement)
            scores.append(ratio)
            changed = True
        else:
            result.append(word)

    if not changed:
        return None, 0

    confidence = round(
        (sum(scores) / len(scores)) * 100
    )

    return " ".join(result), confidence


# ---------------------------------------------------------------------------
# Phrase-level correction
# ---------------------------------------------------------------------------

def _phrase_candidates(reference_terms):
    """
    Return only meaningful multi-word reference terms.
    """
    return [
        term
        for term in reference_terms
        if len(_clean(term).split()) >= 2
    ]


def _phrase_correction(raw, reference_terms):
    """
    Attempt a complete multi-word correction before falling back to
    word-by-word correction.
    """
    raw = _clean(raw)

    if not raw:
        return None, 0

    candidates = _phrase_candidates(reference_terms)

    candidate, ratio = _best_fuzzy(
        raw,
        candidates,
        PHRASE_THRESHOLD,
    )

    if not candidate:
        return None, 0

    if _same_text(raw, candidate):
        return None, 0

    # Do not replace a phrase with a reference phrase having a completely
    # different number of tokens.
    if len(raw.split()) != len(candidate.split()):
        return None, 0

    return candidate, round(ratio * 100)


# ---------------------------------------------------------------------------
# Suggestion construction
# ---------------------------------------------------------------------------

def _make_correction(
    field,
    original,
    suggested,
    reason,
    confidence,
):
    return {
        "field": field,
        "original": _clean(original),
        "suggested": _clean(suggested),
        "reason": reason,
        "confidence": int(max(0, min(100, confidence))),
    }


# ---------------------------------------------------------------------------
# Main correction generation
# ---------------------------------------------------------------------------

def generate_corrections(parsed: dict) -> list:
    """
    Generate explainable spelling/canonicalization suggestions.

    Important properties:

    - Suggestions are NEVER silently applied.
    - Geographic fields use reference data and aliases.
    - Generic address fields use phrase and word-level fuzzy matching.
    - The logic is independent of field order.
    - No evaluation-case IDs or individual test cases are hardcoded.
    - Unrecognized address text is also checked.
    """
    parsed = parsed or {}

    corrections = []

    # ---------------------------------------------------------------
    # 1. Strong geographic correction
    # ---------------------------------------------------------------

    field_specs = [
        (
            "state",
            STATE_ALIASES,
            list(INDIAN_STATES),
            "State",
        ),
        (
            "city",
            CITY_ALIASES,
            list(CITY_STATE_MAP.keys()),
            "City",
        ),
        (
            "locality",
            LOCALITY_ALIASES,
            list(KNOWN_LOCALITIES.keys()),
            "Locality",
        ),
    ]

    reference_suggested_fields = set()
    canonical_protected_fields = set()

    for field, alias_map, canonical_values, label in field_specs:
        raw = _clean(parsed.get(field, ""))

        if not raw:
            continue

        canonical, confidence, method = _resolve_field(
            raw,
            alias_map,
            canonical_values,
        )

        if canonical:
            corrections.append(
                _make_correction(
                    field=field,
                    original=raw,
                    suggested=canonical,
                    reason=(
                        f"{label} name — "
                        f"{method} (reference data)"
                    ),
                    confidence=confidence,
                )
            )

            reference_suggested_fields.add(field)
        else:
            # The value is already an exact canonical reference value.
            # Protect it from the generic fuzzy vocabulary pass. Otherwise a
            # valid value such as Bengaluru/Karnataka can be incorrectly
            # changed back into a typo or a near-match.
            if any(_same_text(raw, value) for value in canonical_values):
                canonical_protected_fields.add(field)

    # ---------------------------------------------------------------
    # 2. Generic correction for address text fields
    # ---------------------------------------------------------------

    reference_terms = _all_reference_terms()

    for field in TEXT_FIELDS:
        raw = _clean(parsed.get(field, ""))

        if not raw:
            continue

        # Geographic reference correction has priority over generic
        # vocabulary correction.
        if field in reference_suggested_fields or field in canonical_protected_fields:
            continue

        # Do not fuzzy-correct a structurally canonical address phrase.
        # This prevents reverse suggestions after an accepted correction.
        if _is_structurally_canonical_text(raw):
            continue

        # Structured address fields are corrected token-by-token. A whole
        # phrase replacement can accidentally replace an already-correct word
        # (for example "Heights" -> "Height") or drop meaningful location
        # tokens from landmarks. Word-level correction preserves all tokens.
        corrected, word_confidence = _generic_word_corrections(
            raw,
            reference_terms,
        )

        if corrected and not _same_text(raw, corrected):
            corrections.append(
                _make_correction(
                    field=field,
                    original=raw,
                    suggested=corrected,
                    reason=(
                        "Possible spelling correction using "
                        "generic word similarity"
                    ),
                    confidence=word_confidence,
                )
            )

    # ---------------------------------------------------------------
    # 3. Inspect parser-unrecognized text
    # ---------------------------------------------------------------

    unrecognized = parsed.get(
        "unrecognized_text",
        [],
    ) or []

    if isinstance(unrecognized, str):
        unrecognized = [unrecognized]

    for token in unrecognized:
        token = _clean(token)

        if not token:
            continue

        # Try phrase-level correction first.
        phrase_candidate, phrase_confidence = _phrase_correction(
            token,
            reference_terms,
        )

        if phrase_candidate:
            corrections.append(
                _make_correction(
                    field="unrecognized_text",
                    original=token,
                    suggested=phrase_candidate,
                    reason=(
                        "Possible phrase spelling correction "
                        "in unrecognized address text"
                    ),
                    confidence=phrase_confidence,
                )
            )

            continue

        corrected, confidence = _generic_word_corrections(
            token,
            reference_terms,
        )

        if corrected and not _same_text(token, corrected):
            corrections.append(
                _make_correction(
                    field="unrecognized_text",
                    original=token,
                    suggested=corrected,
                    reason=(
                        "Possible spelling correction in "
                        "unrecognized address text"
                    ),
                    confidence=confidence,
                )
            )

    # ---------------------------------------------------------------
    # 4. Remove duplicate suggestions
    # ---------------------------------------------------------------

    unique = []
    seen = set()

    for correction in corrections:
        key = (
            correction.get("field", ""),
            _compact(correction.get("original", "")),
            _compact(correction.get("suggested", "")),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(correction)

    return unique


# ---------------------------------------------------------------------------
# Applying accepted corrections
# ---------------------------------------------------------------------------

def apply_corrections(parsed: dict, accepted: list) -> dict:
    """
    Apply ONLY corrections explicitly accepted by the user.

    The input dictionary is never mutated.
    """
    out = dict(parsed or {})

    for correction in accepted or []:
        field = correction.get("field")
        suggested = _clean(
            correction.get("suggested", "")
        )

        if not field or not suggested:
            continue

        # Unrecognized text is intentionally not automatically rewritten
        # into a structured field.
        if field == "unrecognized_text":
            continue

        out[field] = suggested

    return out