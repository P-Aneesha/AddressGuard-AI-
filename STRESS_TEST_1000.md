# AddressGuard AI — 1,000-Case Stress Test Audit

## Scope

The uploaded project contains a labelled evaluation set of 34 seed cases. A deterministic 1,000-case stress dataset was added by applying realistic formatting variants to those 34 labelled cases.

This is a **stress test**, not 1,000 independent real-world addresses.

## What was executed in this sandbox

The dependency-free core validation stack was executed on 1,000 generated cases:

- address parsing
- normalization
- phone validation
- PIN/reference validation
- geographic consistency
- anomaly detection
- confidence scoring
- risk assessment
- final decision engine

External live postal calls were disabled because this sandbox has no network access.

### Core stress result

- Cases: **1,000**
- Correct classifications: **872**
- Core deterministic accuracy: **87.20%**
- Average core processing time: **~16.76 ms/case**

This is **not** the final AddressGuard AI accuracy because the full Flask pipeline and Groq AI correction stage could not be executed in this sandbox.

## Main observed weaknesses

The stress test showed failures mainly in:

1. **Typo/correctable addresses** when AI correction is disabled.
2. Some formatting variants such as labels/newlines causing classification changes.
3. Deterministic correction does not cover all geographic spelling errors; contextual AI/reference correction is intended to fill this gap.

The existing 34-case evaluation already covers the AI-assisted correction scenarios and the uploaded project's stored result reports 100% on that 34-case labelled set. That result was not independently rerun here because the sandbox lacks the project's Flask/SQLAlchemy/OpenAI dependencies.

## Important security issue

The uploaded ZIP contained real-looking credentials in `.env` and also in `.env.example`. The distributed source package therefore replaces these with placeholders.

**Rotate the exposed database password, Groq API key, and Flask secret before using or publishing the project.**

## Full 1,000-case evaluator

Run from the project root:

```powershell
python evaluation\run_1000_stress.py
```

For the expensive AI-enabled version:

```powershell
python evaluation\run_1000_stress.py --ai
```

The evaluator writes:

```text
evaluation\stress_results_1000.json
```

The evaluator calculates metrics from actual pipeline outputs; it does not hardcode accuracy.
