# AddressGuard AI: 250 messy addresses (holdout_7_ai_sample100 set)

Executed 2026-11-01T13:10:37+00:00 (UTC). **82/100 passed (82.0%)**.

**Groq AI was ON** (model openai/gpt-oss-20b); the AI parsed 99 of 100 addresses, the rest fell back to the deterministic parser. External geocoding was off.

**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong PINs). Expected decisions are fixed by construction before the run.

## Key safety numbers

- Addresses that should NOT be verified but were marked VERIFIED: **0 of 70**
- Correct addresses that reached VERIFIED: **24 of 30**
- Time per address: mean 2712.0 ms, median 2535.2 ms, max 7296.7 ms

## By category

| Category | Passed |
|---|---|
| Clean, complete | 7/10 |
| Messy formatting, all correct | 9/10 |
| WhatsApp multi-line, all correct | 8/10 |
| City misspelt | 2/10 |
| State misspelt | 6/10 |
| Phone missing | 10/10 |
| House number and street missing | 10/10 |
| PIN from another state | 10/10 |
| Near-miss PIN (same state, 15-60 km away) | 10/10 |
| Not an address | 10/10 |

## Expected vs actual decision

| Expected | VERIFIED | NEEDS CUSTOMER CONFIRMATION | VALIDATION WARNING | VALIDATION FAILED |
|---|---|---|---|---|
| VERIFIED | 24 | 6 | 0 | 0 |
| NEEDS CUSTOMER CONFIRMATION | 0 | 31 | 9 | 0 |
| VALIDATION WARNING | 0 | 0 | 10 | 0 |
| NEEDS CUSTOMER CONFIRMATION or VALIDATION WARNING | 0 | 10 | 0 | 0 |
| VALIDATION FAILED | 0 | 0 | 0 | 10 |

## Every failure

| ID | Category | Input | Got | Why it failed | Engine's reasons |
|---|---|---|---|---|---|
| M002 | Messy formatting, all correct |   naveen gupta  flat 451 lotus towers  church street chandinchowk cuttack odisha pin - 753 002   ph: +91 7912973887  | NEEDS CUSTOMER CONFIRMATION (94%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M005 | State misspelt | Pooja Joshi, Flat 849, Shanti Nivas, Nehru Street, Chandinchowk, Cuttack, Odisa, 753002, 6165143298 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING |  |
| M010 | Clean, complete | Kavya Patel, Flat 800, Krishna Complex, Main Road, Calicut, Kozhikode, Kerala, 673001, 9485227600 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M012 | WhatsApp multi-line, all correct | Name: Pooja Rao / Mobile: 7382122033 / Address: Flat 389, Sai Residency / 2nd Cross Road, Calicut / Kozhikode - 673001 / Kerala | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M013 | City misspelt | Meera Singh, Flat 680, Royal Heights, 2nd Cross Road, Calicut, Kozhikoode, Kerala, 673001, 8754781117 | NEEDS CUSTOMER CONFIRMATION (86%) | expected city correction to Kozhikode, got none |  |
| M022 | City misspelt | Ananya Singh, Flat 641, Royal Heights, 2nd Cross Road, Rampur Bushahr, Shhimla, Himachal Pradesh, 172001, 6320347933 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING; expected city correction to Shimla, got Raipur Bushahr |  |
| M023 | State misspelt | Lakshmi Menon, Flat 966, Shanti Nivas, Market Road, Rampur Bushahr, Shimla, Himachal Prades, 172001, 6847535601 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING |  |
| M031 | City misspelt | Karthik Das, Flat 909, Royal Heights, Station Road, Sarojini Nagar, Delih, Delhi, 110023, 7565923499 | NEEDS CUSTOMER CONFIRMATION (79%) | expected city correction to Delhi, got none |  |
| M037 | Clean, complete | Divya Rao, Flat 658, Krishna Complex, 2nd Cross Road, Armoor, Nizamabad, Telangana, 503224, 8378490828 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M040 | City misspelt | Ananya Rao, Flat 919, Lotus Towers, 2nd Cross Road, Armoor, Niazmabad, Telangana, 503224, 6933265493 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING; expected city correction to Nizamabad, got none |  |
| M050 | State misspelt | Sneha Gupta, Flat 784, Sunrise Enclave, 2nd Cross Road, Shastri Nagar, Jaipur, Rajastan, 302016, 9274799977 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING |  |
| M057 | WhatsApp multi-line, all correct | Name: Priya Joshi / Mobile: 7556680688 / Address: Flat 175, Shanti Nivas / MG Road, Kottarakara / Kollam - 691506 / Kerala | NEEDS CUSTOMER CONFIRMATION (94%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M058 | City misspelt | Arjun Patel, Flat 977, Sunrise Enclave, Station Road, Kottarakara, Kolam, Kerala, 691506, 6753025528 | NEEDS CUSTOMER CONFIRMATION (86%) | expected city correction to Kollam, got Kottarakkara |  |
| M064 | Clean, complete | Pooja Khan, Flat 775, Krishna Complex, Church Street, Gudur, Tirupati, Andhra Pradesh, 524101, 9214118726 | NEEDS CUSTOMER CONFIRMATION (86%) | expected VERIFIED, got NEEDS CUSTOMER CONFIRMATION |  |
| M067 | City misspelt | Rahul Reddy, Flat 268, Sai Residency, Station Road, Gudur, Tirupait, Andhra Pradesh, 524101, 8562504317 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING; expected city correction to Tirupati, got Guntur |  |
| M068 | State misspelt | Naveen Menon, Flat 349, Shanti Nivas, MG Road, Gudur, Tirupati, Andhra Pradsh, 524101, 8742933425 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING |  |
| M076 | City misspelt | Lakshmi Joshi, Flat 945, Krishna Complex, Market Road, Huzurabad, Kariimnagar, Telangana, 505468, 7147017079 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING; expected city correction to Karimnagar, got none |  |
| M085 | City misspelt | Sanjay Iyer, Flat 163, Silver Oak Residency, Temple Street, Gondal, Raajkot, Gujarat, 360311, 6617995282 | VALIDATION WARNING (50%) | expected NEEDS CUSTOMER CONFIRMATION, got VALIDATION WARNING; expected city correction to Rajkot, got none |  |
