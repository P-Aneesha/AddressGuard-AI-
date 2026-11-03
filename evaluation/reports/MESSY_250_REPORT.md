# AddressGuard AI: 250 messy addresses

Executed 2026-11-03T05:15:17+00:00 (UTC). **249/250 passed (99.6%)**.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were off, so this measures the deterministic engine.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **0 of 175**
- Correct addresses that reached VERIFIED: **75 of 75**
- Time per address: mean 192.6 ms, median 124.8 ms, max 664.9 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 25/25 |
| Messy formatting, all correct | 25/25 |
| WhatsApp multi-line, all correct | 25/25 |
| City misspelt | 24/25 |
| State misspelt | 25/25 |
| Phone missing | 25/25 |
| House number and street missing | 25/25 |
| PIN from another state | 25/25 |
| Near-miss PIN (same state, 15-60 km away) | 25/25 |
| Not an address | 25/25 |

## Expected vs actual decision

| Expected | VERIFIED | NEEDS CUSTOMER CONFIRMATION | VALIDATION WARNING | VALIDATION FAILED |
|---|---|---|---|---|
| VERIFIED | 75 | 0 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 100 | 0 | 0 |
| VALIDATION WARNING | 0 | 0 | 25 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 0 | 25 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 0 | 25 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M076 | City misspelt | Suresh Joshi, Flat 374, Shanti Nivas, 2nd Cross Road, Sarojini Nagar, Dellhi, Delhi, 110023, 7111290845 | NEEDS CUSTOMER CONFIRMATION (94%) | expected city correction to Delhi, got none |  |
