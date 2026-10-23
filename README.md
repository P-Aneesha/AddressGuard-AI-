# AddressGuard AI

**Intelligent Address Validation, Verification & Delivery Risk Assessment Platform**

AddressGuard AI is a human-in-the-loop address validation system for messy Indian address text from WhatsApp, Instagram orders, courier labels, invoices and OCR output. It combines deterministic parsing/normalization, reference-data geography checks, fuzzy correction, optional contextual LLM correction, anomaly detection, confidence/risk reasoning and full re-validation after user decisions.

## Technology Stack

- Frontend: HTML5, CSS3, Vanilla JavaScript
- Backend: Python, Flask
- Database: PostgreSQL (e.g. Neon) + SQLAlchemy — required; there is no other database option
- Allowed techniques: regex, fuzzy matching, rules, pattern recognition, reference datasets, optional external geocoding, PDF/CSV/QR/barcode, password hashing, environment variables
- No React, Node.js, MongoDB, Java, C++, or ML model training

## Local Setup

```bash
cd AddressGuard-AI
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://localhost:5000`.

`DATABASE_URL` must be a PostgreSQL connection string; the app refuses to start without one and prints why. Users and validation history are stored only in PostgreSQL. (The read-only reference lookup index `data/reference_index.sqlite3` is a bundled data file, not the application database.) With `GROQ_API_KEY` absent, the pipeline falls back to deterministic parsing/correction and remains usable.

## Groq AI

Configure in `.env`:

```text
GROQ_API_KEY=your_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
```

The key is server-side only. It is never embedded in frontend JavaScript.

## Optional External Geocoding

External geocoding is disabled by default:

```text
GEOCODING_ENABLED=false
GEOCODING_URL=https://nominatim.openstreetmap.org/search
GEOCODING_TIMEOUT_SECONDS=8
```

When enabled, the corrected address is sent to the configured geocoding service and the result is classified as `CONFIRMED`, `PARTIAL MATCH`, `NOT FOUND`, or `UNAVAILABLE`. A geocoding failure never turns an address into a VALIDATION FAILED result.

The existing reference-data checks remain separate from external verification. A format/reference match is not presented as proof that a physical address exists.

## Human-in-the-Loop Correction Workflow

```text
Raw Address
  ↓
AI Understanding / Parser
  ↓
Normalization
  ↓
Validation + Geographic Checks
  ↓
Anomaly Detection
  ↓
AI + Fuzzy Correction Suggestions
  ↓
Accept / Reject / Edit
  ↓
Apply Decisions
  ↓
Re-parse + Re-normalize
  ↓
Re-validate + Re-check Geography
  ↓
Recalculate Confidence + Risk
  ↓
Final Decision
```

Each correction has Accept / Reject / Edit controls. The dashboard also provides **Accept All** and **Reject All**. Accepted corrections are applied; rejected corrections preserve the original value. Both are resolved for the current review round, so they do not reappear as pending after re-validation. Undecided suggestions remain pending.

After re-validation, the final original/corrected address is displayed in a centered animated notification modal.

## Whole-India Postal / Geographic Reference Data

This project bundles three CSV snapshots supplied for the application:

- `data/india_post_pincode.csv` — 165,627 India-wide postal records with PIN, post office, district, state, taluk and coordinates.
- `data/lgd_villages.csv` — 689,682 LGD village rows; 687,552 non-empty village records are indexed.
- `data/postal_lgd_mapping.csv` — 20,144 PIN-to-LGD state/district mapping rows.

At runtime, `scripts/build_reference_index.py` creates `data/reference_index.sqlite3`. The application queries the index instead of loading the full CSVs into memory. If the index is missing or older than the CSVs, it is rebuilt automatically at application startup.

The reference layer is used for:

- PIN → post office → district/state validation
- village/locality recognition against the LGD roster
- village → sub-district → district → state administrative consistency
- PIN → LGD district/state cross-checking
- spelling/fuzzy suggestions for previously unknown villages/localities

### Important scope

The supplied LGD village CSV does not contain a PIN column. Therefore a village match is not treated as proof of a direct village → PIN relationship. A PIN can still be independently checked against India Post postal data and the village's administrative state/district can be checked against LGD. A dedicated village-with-PIN dataset can be added later if direct village↔PIN verification is required.

Official source documentation:

- India Post / Department of Posts OGD catalog: https://data.gov.in/catalog/all-india-pincode-directory-through-webservice
- Local Government Directory / Ministry of Panchayati Raj: https://data.gov.in/catalog/local-government-directory-lgd
- Official LGD portal: https://lgdirectory.gov.in/

## Additional Reference Data (villages and urban localities)

`python scripts/fetch_reference_data.py` downloads two more datasets into `data/`; the index is rebuilt on the
next start (or run `python scripts/build_reference_index.py`).

| File | Source | Contents |
|---|---|---|
| `data/lgd_villages.csv` | LGD (lgdirectory.gov.in), daily mirror at github.com/ramSeraph/opendata | ~6.8 lakh villages with sub-district, district and state |
| `data/lgd_pincode_villages.csv` | same | village-to-PIN links, so a village can be checked against the supplied PIN |
| `data/osm_localities.csv` | OpenStreetMap via the Overpass API | ~19,700 named suburbs, neighbourhoods and quarters; district/state taken from the nearest India Post office |

OpenStreetMap data © OpenStreetMap contributors, available under the Open Database License (ODbL 1.0).

Coverage limits: OSM is community-mapped, so some well-known areas are missing or tagged under other names
(for example "Salt Lake"), and an OSM locality is only accepted as verified when its district or postcode agrees
with the supplied PIN. No public dataset covers street names or individual buildings.

## Live Whole-India Postal Fallback

The bundled India Post CSV is the primary lookup. If a requested PIN/place is missing from the local snapshot, the optional PincodeAPI.in service can be used as a live fallback when `LIVE_POSTAL_API_ENABLED=true`. It is a third-party service, not an official India Post API.

## Reference Data Commands

Check the supplied CSVs and current index:

```bash
python scripts/check_reference_data.py
```

Rebuild the local index manually:

```bash
python scripts/build_reference_index.py
```

The project no longer requires downloading another dataset after these three CSV files are present.

## Evaluation / Research Experiment

A labelled evaluation dataset is included at:

```text
evaluation/evaluation_dataset.json
```

Run the complete pipeline against it:

```bash
python evaluation/run_evaluation.py
```

For a deterministic run without an LLM API call:

```bash
python evaluation/run_evaluation.py --no-ai
```

The runner measures actual:

- Accuracy
- Macro precision
- Macro recall
- Macro F1-score
- Confusion matrix
- Per-category accuracy
- Correction suggestion accuracy
- Correction recall
- Average and median validation time
- Baseline accuracy using basic format + PIN/phone presence rules
- False positives and false negatives

Results are written to:

```text
evaluation/evaluation_results.json
```

The dashboard reads this file and displays the measured values. Before an experiment has been executed, it explicitly shows:

> Accuracy not yet measured — evaluation dataset/testing is still required.

No performance value is hardcoded.

## Research Interpretation

The project keeps these concepts separate:

- **Confidence:** evidence strength for one address produced by the project's confidence rules.
- **Accuracy:** measured classification performance over the labelled evaluation dataset.
- **External verification:** evidence returned by an external geocoding provider, when enabled.

The project does not claim that a dataset match proves that an address physically exists.

## Decision Labels and Rules

Every result carries one of four labels (defined once in `services/decision_labels.py`):

| Label | Meaning |
|---|---|
| `VERIFIED` | All essential components present and every completed reference check is consistent. |
| `NEEDS CUSTOMER CONFIRMATION` | Plausible, but incomplete, uncertain, or with corrections awaiting review. |
| `VALIDATION WARNING` | A reference check found a concrete conflict (e.g. PIN vs state) that needs manual review. |
| `VALIDATION FAILED` | The text has no recognisable address structure. |

Older releases used `SUSPICIOUS` / `NEEDS VERIFICATION` and `FAKE ADDRESS`. Stored records are renamed on
startup by an idempotent, non-destructive update, and any remaining legacy value is mapped when read.

`services/decision_engine.py` applies ordered rules; the first match decides and its id is shown in the
decision reasoning:

- **D1 → VALIDATION FAILED** — no recognisable address structure.
- **D2 → VALIDATION WARNING** — critical risk backed by concrete conflicting evidence.
- **D3 → VALIDATION WARNING** — a reference dataset reports a hard geographic conflict.
- **D4 → VALIDATION WARNING** — high-severity anomaly (placeholder PIN, mostly unrecognised text).
- **D5 → VERIFIED** — all essentials present, PIN confirmed in postal reference data, no conflicts, no pending corrections, reference data available.
- **D6 → NEEDS CUSTOMER CONFIRMATION** — everything else. Missing or unverifiable data is uncertainty, never proof of an invalid address.

Confidence (address completeness/consistency) and delivery risk are separate scores. Confidence is capped
at 50% when a geographic conflict exists and at 79% when essential data is missing or reference data is
unavailable; each cap is listed in the confidence evidence. Spelling suggestions alone cannot raise delivery
risk above LOW.

PIN handling distinguishes a missing PIN, a format error (wrong length, leading 0, repeated digits), and a
well-formed PIN that the reference data cannot confirm (reported as unconfirmed, not invalid).

## Tests

```bash
python -m pytest tests/ -v                  # full suite (uses a temporary database, never the real one)
python evaluation/run_30_cases.py           # 30 documented cases -> evaluation/TEST_30_CASES.md
python evaluation/run_evaluation.py --no-ai # 34 labelled cases, deterministic
python evaluation/run_1000_stress.py        # 1,000 synthetic variants
python evaluation/run_messy_250.py          # 250 messy addresses -> evaluation/MESSY_250_REPORT.md
python evaluation/messy_addresses.py 7      # build an independent holdout set (seed 7)
python evaluation/run_messy_250.py evaluation/messy_250_holdout_7.json
```

`tests/test_30_address_cases.py` covers valid addresses, spelling errors, missing fields, invalid PINs,
geographic mismatches, unusual input, empty/long/malformed input, and injected database, pipeline, Groq,
geocoder and reference-data failures. The evaluation datasets were written alongside the system, so their
scores show consistency with the documented rules rather than independent real-world accuracy.

The 250-address sets are generated from real India Post delivery offices (real localities, PINs, cities and
states; synthetic names, phones and streets) written in messy ways: no punctuation, WhatsApp layout, typos,
missing parts, PINs from another state, near-miss PINs and non-addresses. They are not real customer data.
The engine was tuned while looking at the seed-2026 set, so the seed-7 holdout is the fairer number.

## Rate limiting

Login (10 per 5 minutes per IP), registration (5 per hour per IP) and validation (30 per minute and 500 per
day per user) are limited. Hits are counted in the `rate_limit_hits` table, so limits hold across serverless
instances. Exceeding a limit returns HTTP 429 with a `Retry-After` header. Override a limit with e.g.
`RATELIMIT_VALIDATE=60/60`; limits are off in automated tests unless `RATELIMIT_ENABLED=1`.

## Database (Neon PostgreSQL)

Set:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE
```

Tables are created automatically for development. Flask-Migrate is included for schema migration workflows.

## Deployment (Vercel)

The raw CSVs (about 200 MB) and the uncompressed index (226 MB) are not deployed; `.vercelignore` excludes
them. Instead the app ships `data/reference_index.sqlite3.gz` (about 49 MB) and unpacks it into the temp
folder on a cold start (about 1-3 s).

```bash
python scripts/package_reference_index.py   # after any index rebuild
vercel login
vercel link
python scripts/vercel_env_sync.py           # copies .env settings; generates a new SECRET_KEY
vercel deploy --prod
```

On Vercel the app refuses to start without a random `SECRET_KEY` of at least 32 characters, sends session
cookies only over HTTPS, and skips the local DNS workaround. Reports are generated in memory and streamed,
so the application does not depend on a writable deployment filesystem.

## Core Pipeline

1. AI Address Understanding
2. Address Parsing
3. Data Normalization
4. Phone Validation
5. PIN Validation
6. City & State Validation
7. Locality Validation
8. Address Pattern Validation
9. Geographic Consistency
10. External Geocoding Verification (optional)
11. Anomaly Detection
12. AI Spelling Correction
13. Context-Aware Address Resolution
14. Confidence & Final Decision


## Research Evaluation

AddressGuard includes a reproducible labelled evaluation system. It does not
hardcode accuracy or research performance.

Run a normal evaluation:

```powershell
python evaluation/run_evaluation.py
```

Run without Groq/LLM calls:

```powershell
python evaluation/run_evaluation.py --no-ai
```

Run automated tests:

```powershell
python -m pytest tests -v
```

Results are written to:

```text
evaluation/evaluation_results.json
```

The evaluation reports:

- dataset size and successful/failed runs
- accuracy
- macro precision
- macro recall
- macro F1
- confusion matrix
- per-category accuracy
- correction suggestion accuracy and recall
- average and median validation time
- false positives and false negatives
- baseline comparison on the same dataset
- controlled before/after experiment using labelled expected corrections

Human correction acceptance rate is intentionally reported as **not measured**
unless real human review decisions have been recorded. It is never inferred
from correction accuracy.

### Confidence vs accuracy

The address confidence score is evidence for one address. It is not the same
thing as statistical accuracy over the evaluation dataset.

### Geographic verification

The pipeline distinguishes reference-data geographic consistency from optional
external geocoding. An unavailable geocoding provider does not automatically
make an address fake.

### Human-in-the-loop re-validation

Corrections can be accepted, rejected, or manually edited individually.
Accept All and Reject All are also available. Accepted and rejected decisions
are treated as resolved for that review round, so they do not reappear as
pending corrections after re-validation. Undecided corrections remain pending.

### Research claims

Only values generated by `evaluation/run_evaluation.py` should be reported as
experimental results. Do not claim physical address verification unless an
actual external verification source supports that statement.

## Whole-India official-reference datasets

The project can populate the full reference layer with:

```bash
python -m pip install -r requirements.txt
python scripts/download_reference_datasets.py
```

The command creates:

- `data/india_post_pincode.csv` — all-India India Post pincode directory mirror (2026)
- `data/lgd_villages_with_pin.csv` — LGD village-to-PIN mapping
- `data/lgd_admin.csv` — LGD state/district/sub-district hierarchy

Large data files are intentionally not committed to Git. The runtime uses these files automatically when present and falls back to the small built-in references only when they are absent.

The India Post authoritative source is the Government of India OGD **All India Pincode Directory**, Department of Posts. The LGD authoritative source is the Government of India OGD **Local Government Directory**, Ministry of Panchayati Raj. The downloadable LGD exports are obtained through the versioned LGD data mirror documented in `data/SOURCES.md`.

## Live Whole-India Postal Verification

AddressGuard can now perform live whole-India PIN/post-office/place-name checks through the public PincodeAPI.in V1 service when `LIVE_POSTAL_API_ENABLED=true`. The service documents PIN lookup, state lookup, district lookup, and post-office/place-name search and currently provides a free Starter plan subject to a 6-calls-per-10-seconds per-IP limit and fair-use terms.

This live service is **not an India Post government API**. It is a third-party postal directory that states its data is sourced from Department of Posts data. The project still supports the official data.gov.in API when `DATA_GOV_API_KEY` and `DATA_GOV_PINCODE_RESOURCE_ID` are configured, and local India Post/LGD CSV snapshots remain an offline fallback.

For reproducible academic evidence, cite the official Government of India India Post directory and LGD sources in `data/SOURCES.md`; use the live API only as the runtime refresh/lookup layer.

## Whole-India reference data setup

For a complete local reference snapshot, run `DOWNLOAD_REFERENCE_DATASETS.bat` once. It downloads all India postal pages through the public PincodeAPI.in directory and the latest LGD export release, then writes `data/india_post_pincode.csv`, `data/lgd_villages_with_pin.csv`, and `data/lgd_admin.csv`.

For normal online operation, keep these values in `.env`:

```env
LIVE_POSTAL_API_ENABLED=true
LIVE_POSTAL_API_BASE_URL=https://api.pincodeapi.in/api/v1
LIVE_POSTAL_API_TIMEOUT=8
LIVE_POSTAL_CACHE_TTL_SECONDS=600
OFFICIAL_REFERENCE_ENABLED=true
```

The live postal API is a third-party service based on India Post/OGD-derived public postal data; it is not an official India Post API.

### Geographic verification fallback
The geographic layer treats missing optional hierarchy fields (such as an omitted district) as INCOMPLETE without downgrading an otherwise consistent postal/geographic result. City comparisons also understand administrative naming variants such as `Bengaluru` vs `Bengaluru Urban`.

External geocoding via Nominatim/OpenStreetMap remains optional. If Nominatim has no precise result, the pipeline falls back to the bundled nationwide India Post postal coordinates for PIN/state/city context and reports `PARTIAL MATCH` transparently rather than a false warning. This fallback does not claim building-level existence.


## Whole-India dataset integration and spelling correction

AddressGuard AI uses the supplied whole-India reference files at runtime through `data/reference_index.sqlite3`:

- `data/india_post_pincode.csv` — postal offices, PIN, district, state, taluk and coordinates.
- `data/lgd_villages.csv` — LGD village and administrative hierarchy.
- `data/postal_lgd_mapping.csv` — PIN-to-LGD state/district cross-check.

The correction pipeline is hybrid: whole-India reference matching is used for geographic fields, fuzzy similarity detects likely misspellings, and Groq AI provides context-aware suggestions for address text that is not represented by the official reference data. Corrections are suggestions only and require human approval before a complete re-validation.

### Evaluation

Run the reproducible deterministic evaluation from the project root:

```bash
python evaluation/run_evaluation.py --no-ai
```

The existing 34-case labelled evaluation is used to calculate classification accuracy, macro precision/recall/F1, correction precision/accuracy, correction recall/F1, and validation time. Reported values are generated by the evaluation script and must not be treated as real-world accuracy.
