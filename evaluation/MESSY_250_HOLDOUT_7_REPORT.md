# AddressGuard AI: 250 messy addresses (holdout_7 set)

Executed 2026-10-22T17:44:59+00:00 (UTC). **237/250 passed (94.8%)**.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were off, so this measures the deterministic engine.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **0 of 175**
- Correct addresses that reached VERIFIED: **69 of 75**
- Time per address: mean 152.3 ms, median 72.9 ms, max 414.6 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 23/25 |
| Messy formatting, all correct | 23/25 |
| WhatsApp multi-line, all correct | 23/25 |
| City misspelt | 23/25 |
| State misspelt | 23/25 |
| Phone missing | 25/25 |
| House number and street missing | 25/25 |
| PIN from another state | 25/25 |
| Near-miss PIN (same state, 15-60 km away) | 25/25 |
| Not an address | 22/25 |

## Expected vs actual decision

| Expected | VERIFIED | NEEDS CUSTOMER CONFIRMATION | VALIDATION WARNING | VALIDATION FAILED |
|---|---|---|---|---|
| VERIFIED | 69 | 6 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 100 | 0 | 0 |
| VALIDATION WARNING | 0 | 0 | 25 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 0 | 25 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 3 | 22 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M032 | State misspelt | Aditya Gupta, Flat 263, Lotus Towers, 2nd Cross Road, Sarojini Nagar, Delhi, Dehli, 110023, 6878246640 | NEEDS CUSTOMER CONFIRMATION (94%) | expected state correction to Delhi, got none |  |
| M067 | City misspelt | Rahul Reddy, Flat 268, Sai Residency, Station Road, Gudur, Tirupait, Andhra Pradesh, 524101, 8562504317 | NEEDS CUSTOMER CONFIRMATION (86%) | expected city correction to Tirupati, got Guntur |  |
| M121 | City misspelt | Rohan Joshi, Flat 799, Krishna Complex, Main Road, Sarojini Nagar, Nwe Delhi, Delhi, 110023, 9489038017 | NEEDS CUSTOMER CONFIRMATION (100%) | expected city correction to New Delhi, got none |  |
| M122 | State misspelt | Naveen Reddy, Flat 306, Shanti Nivas, Main Road, Sarojini Nagar, New Delhi, Dehli, 110023, 7632249109 | NEEDS CUSTOMER CONFIRMATION (94%) | expected state correction to Delhi, got none |  |
| M145 | Clean, complete | Divya Joshi, Flat 962, Shanti Nivas, Temple Street, Gurgaon, Gurugram, Haryana, 122001, 6937250820 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M146 | Messy formatting, all correct |   imran rao  flat 361 shanti nivas  main road gurgaon gurugram haryana pin - 122 001   ph: +91 8500474606  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M147 | WhatsApp multi-line, all correct | Name: Aditya Khan / Mobile: 7363432139 / Address: Flat 342, Lotus Towers / Temple Street, Gurgaon / Gurugram - 122001 / Haryana | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M172 | Clean, complete | Naveen Das, Flat 104, Silver Oak Residency, Church Street, Barabazar H O, Kolkata, West Bengal, 700007, 7125099022 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M173 | Messy formatting, all correct |   divya das  flat 284 silver oak residency  gandhi nagar road barabazar h o kolkata west bengal pin - 700 007   ph: +91 9998233518  | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M174 | WhatsApp multi-line, all correct | Name: Sneha Reddy / Mobile: 7485017052 / Address: Flat 541, Royal Heights / Station Road, Barabazar H O / Kolkata - 700007 / West Bengal | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M228 | Not an address | test test 123 | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
| M233 | Not an address | 1234567890 | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
| M234 | Not an address | lorem ipsum dolor sit amet | VALIDATION WARNING (14%) | expected VALIDATION FAILED, got VALIDATION WARNING |  |
