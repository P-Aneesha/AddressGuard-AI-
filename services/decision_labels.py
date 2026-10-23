"""Single source of truth for AddressGuard decision labels.

Older releases stored "SUSPICIOUS" / "NEEDS VERIFICATION" and "FAKE ADDRESS".
Those values are mapped to the current labels so historical records stay
readable and countable after the rename.
"""

VERIFIED = "VERIFIED"
NEEDS_CONFIRMATION = "NEEDS CUSTOMER CONFIRMATION"
VALIDATION_WARNING = "VALIDATION WARNING"
VALIDATION_FAILED = "VALIDATION FAILED"

DECISIONS = [VERIFIED, NEEDS_CONFIRMATION, VALIDATION_WARNING, VALIDATION_FAILED]

LEGACY_DECISIONS = {
    "SUSPICIOUS": VALIDATION_WARNING,
    "NEEDS VERIFICATION": VALIDATION_WARNING,
    "FAKE ADDRESS": VALIDATION_FAILED,
}

DECISION_DESCRIPTIONS = {
    VERIFIED: "All essential components are present and every completed reference check is consistent.",
    NEEDS_CONFIRMATION: "The address is plausible but incomplete, uncertain, or has corrections awaiting confirmation.",
    VALIDATION_WARNING: "A reference check found a concrete conflict (for example PIN vs state) that needs manual review.",
    VALIDATION_FAILED: "The text does not contain enough recognisable address structure to validate.",
}


def normalize_decision(value):
    """Map any legacy label to its current equivalent; pass current labels through."""
    text = str(value or "").strip().upper()
    return LEGACY_DECISIONS.get(text, text)
