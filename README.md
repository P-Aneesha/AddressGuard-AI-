# AddressGuard AI

**Intelligent Address Validation, Verification & Delivery Risk Assessment Platform**

AddressGuard AI is a human-in-the-loop address validation system for messy Indian address text from WhatsApp, Instagram orders, courier labels, invoices and OCR output. It combines deterministic parsing/normalization, reference-data geography checks, fuzzy correction, optional contextual LLM correction, anomaly detection, confidence/risk reasoning and full re-validation after user decisions.

## Technology Stack

- Frontend: HTML5, CSS3, Vanilla JavaScript
- Backend: Python, Flask
- Database: PostgreSQL/Neon + SQLAlchemy; local SQLite fallback for development
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

Without `DATABASE_URL`, the project uses local SQLite for development. With `GROQ_API_KEY` absent, the pipeline falls back to deterministic parsing/correction and remains usable.

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

When enabled, the corrected address is sent to the configured geocoding service and the result is classified as `CONFIRMED`, `PARTIAL MATCH`, `NOT FOUND`, or `UNAVAILABLE`. A geocoding failure does not turn an address into a fake address.

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

## Tests

```bash
python -m pytest tests/ -v
```

## Database (Neon PostgreSQL)

Set:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE
```

Tables are created automatically for development. Flask-Migrate is included for schema migration workflows.

## Deployment (Vercel)

Set these environment variables in the deployment platform:

```text
SECRET_KEY
DATABASE_URL
GROQ_API_KEY
GROQ_BASE_URL
GROQ_MODEL
GROQ_TIMEOUT_SECONDS
GEOCODING_ENABLED
GEOCODING_URL
GEOCODING_TIMEOUT_SECONDS
OFFICIAL_REFERENCE_ENABLED
INDIA_POST_PINCODE_CSV
LGD_VILLAGES_CSV
POSTAL_LGD_MAPPING_CSV
REFERENCE_INDEX_DB
DATA_GOV_API_KEY
DATA_GOV_PINCODE_RESOURCE_ID
OFFICIAL_REFERENCE_TIMEOUT
```

Reports are generated in memory and streamed, so the application does not depend on a writable deployment filesystem.

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
