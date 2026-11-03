# AddressGuard AI: 250 messy addresses (holdout_7 set)

Executed 2026-11-01T14:06:28+00:00 (UTC). **243/250 passed (97.2%)**.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were off, so this measures the deterministic engine.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **0 of 175**
- Correct addresses that reached VERIFIED: **69 of 75**
- Time per address: mean 246.1 ms, median 183.6 ms, max 1627.5 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 23/25 |
| Messy formatting, all correct | 23/25 |
| WhatsApp multi-line, all correct | 23/25 |
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
| VERIFIED | 69 | 6 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 100 | 0 | 0 |
| VALIDATION WARNING | 0 | 0 | 25 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 0 | 25 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 0 | 25 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M031 | City misspelt | Karthik Das, Flat 909, Royal Heights, Station Road, Sarojini Nagar, Delih, Delhi, 110023, 7565923499 | NEEDS CUSTOMER CONFIRMATION (94%) | expected city correction to Delhi, got none |  |
| M145 | Clean, complete | Divya Joshi, Flat 962, Shanti Nivas, Temple Street, Gurgaon, Gurugram, Haryana, 122001, 6937250820 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M146 | Messy formatting, all correct |   imran rao  flat 361 shanti nivas  main road gurgaon gurugram haryana pin - 122 001   ph: +91 8500474606  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M147 | WhatsApp multi-line, all correct | Name: Aditya Khan / Mobile: 7363432139 / Address: Flat 342, Lotus Towers / Temple Street, Gurgaon / Gurugram - 122001 / Haryana | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M172 | Clean, complete | Naveen Das, Flat 104, Silver Oak Residency, Church Street, Barabazar H O, Kolkata, West Bengal, 700007, 7125099022 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M173 | Messy formatting, all correct |   divya das  flat 284 silver oak residency  gandhi nagar road barabazar h o kolkata west bengal pin - 700 007   ph: +91 9998233518  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M174 | WhatsApp multi-line, all correct | Name: Sneha Reddy / Mobile: 7485017052 / Address: Flat 541, Royal Heights / Station Road, Barabazar H O / Kolkata - 700007 / West Bengal | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
