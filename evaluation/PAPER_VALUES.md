# Values for the research paper (measured 1 Nov 2026)

## Corrections to the current PDF
- Development set before fixes: **164/249 = 65.9%** (not 164/250 = 65.6%; that run had 249 cases).
- Automated tests: **142** (not 110).

## Table I — Messy-address evaluation (Groq AI and geocoding off unless stated)
| Evaluation | Correct/Total | Accuracy | Invalid marked VERIFIED |
|---|---|---|---|
| Development, before fixes | 164/249 | 65.9% | 3 |
| Development, first fixes | 241/250 | 96.4% | 0 |
| Holdout (seed 7), first fixes | 237/250 | 94.8% | 0 |
| Development, second fixes | 249/250 | 99.6% | 0 |
| Holdout (seed 7), second fixes | 242/250 | 96.8% | 0 |
| Model enabled, holdout sample of 100 (before AI fixes) | 82/100 | 82.0% | 0 |
| **Final fresh holdout (seed 11), run once** | **246/250** | **98.4%** | **1** |

Notes:
- After the AI fixes (tuned on seed-7 AI failures) the seed-7 deterministic score was 243/250 (97.2%); seed 7 is no longer independent.
- AI-mode re-run of the 18 failed sample cases after the AI fixes: 14/18 passed.
- The one false VERIFIED in the final holdout: "Dadar, Mumbai, Maharashtra, 402107". PIN 402107 belongs to a different village named Dadar in Raigad district (adjacent to Mumbai); the PIN has a post office named "Dadar" within the 25 km city-area radius, so the near-miss check accepted it. Failure mode: same-name places in neighbouring districts.
- The other 3 final-holdout failures: "Gurgaon, Gurugram" (old city name as locality) suggested as a city correction; decision NEEDS CUSTOMER CONFIRMATION.

## Other evaluations
- 34-case labelled evaluation: 100% classification, 100% correction, 100% after-correction.
- 30-case functional suite: 30/30.
- 142 automated tests pass.

## Reference data
- India Post offices: 165,625. Post offices whose names could not match before the suffix fix: 76,150 (46%).
- LGD villages: 677,666; village-PIN links: 672,609; postal-LGD mapping rows: 20,144.
- OpenStreetMap localities: **48,643** (was 19,664).
- OpenStreetMap named roads: **185,944** across 37 states/UTs (Geofabrik extracts; state = majority of nearest 7 post offices within 20 km).
- Reference index: **258 MB** unpacked, **60.2 MB** gzip (was 226 MB / 48.8 MB).

## Near-miss calibration
- 283 OSM localities with their own PIN: 90% within 4.9 km of an office of that PIN; ~6% over 30 km.
- Rule: all offices of the PIN > 10 km away, another PIN's office within 2 km, no office of the PIN named after the locality. Confidence capped at 79%.
- City-area radius: 25 km. Street "near PIN": 5 km. PIN suggestion via nearest office: within 1.5 km.

## Performance
- One validation before speedups: ~4.9 s (geocoder 1.97 s, AI extraction 1.81 s).
- After speedups: new address ~2.2 s; repeated address ~0.6–1.2 s.
- Re-validation after review skips both AI calls (~3 s saved).
- 26 reference lookups per validation (~0.6 s locally); Neon round trip from India: median 224 ms.
- Local Vercel simulation cold start: 2.7 s (measured with the earlier 48.8 MB archive).

## Groq free tier
- 1,000 requests/day, 8,000 tokens/minute, 200,000 tokens/day.
- ~1,800 tokens per validation → about 110 AI-assisted validations/day.

## Rate limits
- Login 10 per 5 min per IP; registration 5 per hour per IP; validation 30/min and 500/day per user; bulk 5 files/hour (50 addresses each).
