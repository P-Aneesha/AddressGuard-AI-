# AddressGuard AI: 250 messy addresses

Executed 2026-10-22T17:44:19+00:00 (UTC). **241/250 passed (96.4%)**.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were off, so this measures the deterministic engine.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **0 of 175**
- Correct addresses that reached VERIFIED: **72 of 75**
- Time per address: mean 152.0 ms, median 71.8 ms, max 421.6 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 24/25 |
| Messy formatting, all correct | 24/25 |
| WhatsApp multi-line, all correct | 24/25 |
| City misspelt | 24/25 |
| State misspelt | 23/25 |
| Phone missing | 25/25 |
| House number and street missing | 25/25 |
| PIN from another state | 25/25 |
| Near-miss PIN (same state, 15-60 km away) | 25/25 |
| Not an address | 22/25 |

## Expected vs actual decision

| Expected | VERIFIED | NEEDS CUSTOMER CONFIRMATION | VALIDATION WARNING | VALIDATION FAILED |
|---|---|---|---|---|
| VERIFIED | 72 | 3 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 100 | 0 | 0 |
| VALIDATION WARNING | 0 | 0 | 25 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 0 | 25 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 3 | 22 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M077 | State misspelt | Ayesha Gupta, Flat 447, Sai Residency, MG Road, Sarojini Nagar, Delhi, Dehli, 110023, 9618528950 | NEEDS CUSTOMER CONFIRMATION (94%) | expected state correction to Delhi, got none |  |
| M094 | City misspelt | Ayesha Joshi, Flat 722, Lotus Towers, 2nd Cross Road, Sarojini Nagar, Neww Delhi, Delhi, 110023, 7263201014 | NEEDS CUSTOMER CONFIRMATION (100%) | expected city correction to New Delhi, got none |  |
| M095 | State misspelt | Sanjay Sharma, Flat 909, Shanti Nivas, 2nd Cross Road, Sarojini Nagar, New Delhi, Dehli, 110023, 6401041973 | NEEDS CUSTOMER CONFIRMATION (94%) | expected state correction to Delhi, got none |  |
| M145 | Clean, complete | Aditya Rao, Flat 491, Sai Residency, Church Street, Anna Road, Chennai, Tamil Nadu, 600002, 8261667834 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M146 | Messy formatting, all correct |   sanjay reddy  flat 952 royal heights  church street anna road chennai tamil nadu pin - 600 002   ph: +91 6344194468  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M147 | WhatsApp multi-line, all correct | Name: Arjun Gupta / Mobile: 8571135106 / Address: Flat 888, Silver Oak Residency / Temple Street, Anna Road / Chennai - 600002 / Tamil Nadu | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M228 | Not an address | test test 123 | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
| M233 | Not an address | 1234567890 | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
| M234 | Not an address | lorem ipsum dolor sit amet | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
