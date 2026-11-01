# AddressGuard AI: 250 messy addresses (holdout_11 set)

Executed 2026-11-01T14:07:41+00:00 (UTC). **246/250 passed (98.4%)**.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were off, so this measures the deterministic engine.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **1 of 175**
- Correct addresses that reached VERIFIED: **72 of 75**
- Time per address: mean 279.0 ms, median 220.6 ms, max 1012.9 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 24/25 |
| Messy formatting, all correct | 24/25 |
| WhatsApp multi-line, all correct | 24/25 |
| City misspelt | 25/25 |
| State misspelt | 25/25 |
| Phone missing | 25/25 |
| House number and street missing | 25/25 |
| PIN from another state | 25/25 |
| Near-miss PIN (same state, 15-60 km away) | 24/25 |
| Not an address | 25/25 |

## Expected vs actual decision

| Expected | VERIFIED | NEEDS CUSTOMER CONFIRMATION | VALIDATION WARNING | VALIDATION FAILED |
|---|---|---|---|---|
| VERIFIED | 72 | 3 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 100 | 0 | 0 |
| VALIDATION WARNING | 0 | 0 | 25 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 1 | 24 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 0 | 25 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M037 | Clean, complete | Meera Gupta, Flat 423, Silver Oak Residency, 5th Main Road, Gurgaon, Gurugram, Haryana, 122001, 9821712668 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M038 | Messy formatting, all correct |   arjun sharma  flat 143 shanti nivas  nehru street gurgaon gurugram haryana pin - 122 001   ph: +91 8752356729  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M039 | WhatsApp multi-line, all correct | Name: Fatima Patel / Mobile: 6788252991 / Address: Flat 240, Krishna Complex / Church Street, Gurgaon / Gurugram - 122001 / Haryana | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M072 | Near-miss PIN (same state, 15-60 km away) | Karthik Iyer, Flat 790, Green Park Apartments, Nehru Street, Dadar, Mumbai, Maharashtra, 402107, 7403970346 | VERIFIED (100%) | expected NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING, got VERIFIED |  |
