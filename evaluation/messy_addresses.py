"""Generate the 250-address messy evaluation set from real reference places.

These are NOT real customer addresses. Every locality, PIN, city and state
comes from the India Post reference data (real post offices in 62 known
cities); names, phone numbers, house numbers and streets are synthetic. Each
address is then written the way people actually type addresses (typos, no
punctuation, WhatsApp layout, missing parts, wrong PINs). The expected
decision is fixed by how each variant is constructed, before the system runs.

Run: python evaluation/messy_addresses.py  -> writes evaluation/messy_250_dataset.json
"""
import json
import math
import random
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.indian_data import CITY_ALIASES, CITY_STATE_MAP  # noqa: E402

VERIFIED = "VERIFIED"
NCC = "NEEDS CUSTOMER CONFIRMATION"
WARNING = "VALIDATION WARNING"
FAILED = "VALIDATION FAILED"

SEED = 2026
BASES_PER_RUN = 25
DATASET = ROOT / "evaluation" / "messy_250_dataset.json"

FIRST = ["Rahul", "Priya", "Arjun", "Sneha", "Vikram", "Ananya", "Karthik", "Divya", "Imran", "Lakshmi",
         "Rohan", "Fatima", "Suresh", "Meera", "Aditya", "Pooja", "Naveen", "Kavya", "Sanjay", "Ayesha"]
LAST = ["Sharma", "Reddy", "Iyer", "Khan", "Patel", "Nair", "Gupta", "Das", "Singh", "Rao", "Menon", "Joshi"]
BUILDINGS = ["Sai Residency", "Green Park Apartments", "Lotus Towers", "Sunrise Enclave", "Shanti Nivas",
             "Royal Heights", "Krishna Complex", "Silver Oak Residency"]
STREETS = ["MG Road", "Station Road", "2nd Cross Road", "Main Road", "Temple Street", "5th Main Road",
           "Gandhi Nagar Road", "Church Street", "Market Road", "Nehru Street"]
STATE_TYPOS = {
    "Telangana": "Telengana", "Karnataka": "Karnatka", "Maharashtra": "Maharastra", "Tamil Nadu": "Tamilnadu",
    "West Bengal": "West Bangal", "Kerala": "Kerela", "Rajasthan": "Rajastan", "Gujarat": "Gujrat",
    "Uttar Pradesh": "Uttar Pradsh", "Andhra Pradesh": "Andhra Pradsh", "Madhya Pradesh": "Madhya Pradsh",
    "Odisha": "Odisa", "Bihar": "Bihaar", "Punjab": "Panjab", "Haryana": "Hariyana", "Assam": "Asam",
    "Jharkhand": "Jharkand", "Chhattisgarh": "Chattisgarh", "Delhi": "Dehli", "Goa": "Gooa",
    "Uttarakhand": "Uttrakhand", "Chandigarh": "Chandigar",
}
GARBAGE = [
    "hello bro how are you", "asdf qwer zxcv", "test test 123", "ok", "please call me", "sdfgh jkl poiuy",
    "!!!!!!", "1234567890", "lorem ipsum dolor sit amet", "send the parcel fast", "aaaaaaaaaaaa",
    "xyz abc pqr", "my address is same as before", "where is my order", "qwerty", "na", "..........",
    "hi", "zzzz yyyy xxxx", "delivery tomorrow ok", "random text here nothing", "abc 000000",
    "mnbvcxz lkjhgf", "same", "thank you",
]


def _km(a, b):
    dx = (b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(b[0] - a[0], dx) * 111.2


def _locality(officename):
    name = re.sub(r"\(.*?\)", "", officename)
    name = re.sub(r"\b(S\.?O|H\.?O|B\.?O|SO|HO|BO)\b\.?", "", name, flags=re.I)
    return " ".join(name.replace(".", " ").split()).title()


def _city_typo(city, rng):
    known = {c.lower() for c in CITY_STATE_MAP} | set(CITY_ALIASES)
    for _ in range(50):
        i = rng.randrange(1, len(city) - 1)
        typo = rng.choice([
            city[:i] + city[i + 1:],                          # dropped letter
            city[:i] + city[i + 1] + city[i] + city[i + 2:],  # swapped letters
            city[:i] + city[i] + city[i:],                    # doubled letter
        ])
        if typo.lower() not in known and typo.lower() != city.lower():
            return typo
    return city[:-1]


def _bases(con, rng):
    by_city = {}
    for office, pin, district, state, lat, lon in con.execute(
        "SELECT officename, pincode, district, statename, latitude, longitude FROM postal_offices "
        "WHERE (officetype LIKE 'S%' OR officetype LIKE 'H%') AND delivery LIKE 'Deliv%'"
    ):
        for city, city_state in CITY_STATE_MAP.items():
            if city.lower() in str(district).lower() and city_state.lower() == str(state).lower().replace("&", "and"):
                loc = _locality(office)
                # Head offices named after the city ("Kollam", "Amritsar GPO") are not
                # how people name their neighbourhood, so only distinct localities are used.
                if loc and not re.search(r"\d", loc) and 4 <= len(loc) <= 24 and city.lower() not in loc.lower() \
                        and not re.search(r"\b(?:gpo|ho|cantt|court|secretariat|collectorate)\b", loc, re.I):
                    by_city.setdefault(city, []).append((loc, pin, city, city_state, lat, lon))
    cities = sorted(by_city)
    rng.shuffle(cities)
    bases = []
    while len(bases) < BASES_PER_RUN:
        city = cities[len(bases) % len(cities)]
        bases.append(rng.choice(by_city[city]))
    return bases


def _person(rng):
    return (f"{rng.choice(FIRST)} {rng.choice(LAST)}", f"{rng.choice('6789')}{rng.randrange(10**8, 10**9)}",
            f"Flat {rng.randrange(101, 999)}", rng.choice(BUILDINGS), rng.choice(STREETS))


def _other_state_pin(con, state, rng):
    rows = con.execute("SELECT pincode FROM postal_offices WHERE statename<>? AND statename<>? ORDER BY RANDOM() LIMIT 1",
                       (state, state.upper())).fetchall()
    return rows[0][0]


def _near_miss_pin(con, base, offices_by_state):
    """A real PIN of the same state whose post offices are all 15-60 km away."""
    loc, pin, city, state, lat, lon = base
    try:
        origin = (float(lat), float(lon))
    except (TypeError, ValueError):
        return None
    best = {}
    for other_pin, point in offices_by_state.get(state.lower(), []):
        if other_pin == pin:
            continue
        d = _km(origin, point)
        best[other_pin] = min(d, best.get(other_pin, 1e9))
    candidates = sorted(p for p, d in best.items() if 15 <= d <= 60)
    return candidates[len(candidates) // 2] if candidates else None


def build(seed=SEED, path=DATASET):
    rng = random.Random(seed)
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'reference_index.sqlite3'}?mode=ro", uri=True)
    bases = _bases(con, rng)
    offices_by_state = {}
    for p, st, la, lo in con.execute("SELECT pincode, statename, latitude, longitude FROM postal_offices"):
        try:
            offices_by_state.setdefault(str(st).lower().replace("&", "and"), []).append((p, (float(la), float(lo))))
        except (TypeError, ValueError):
            pass

    cases = []

    def add(category, text, expect, base=None, **extra):
        cases.append({"id": f"M{len(cases) + 1:03d}", "category": category, "input": text,
                      "expect_decision_in": expect, "source_place": base and {
                          "locality": base[0], "pin": base[1], "city": base[2], "state": base[3]}, **extra})

    for b in bases:
        loc, pin, city, state, *_ = b
        name, phone, flat, building, street = _person(rng)
        add("Clean, complete", f"{name}, {flat}, {building}, {street}, {loc}, {city}, {state}, {pin}, {phone}",
            [VERIFIED], b)
        name, phone, flat, building, street = _person(rng)
        add("Messy formatting, all correct",
            f"  {name.lower()}  {flat.lower()} {building.lower()}  {street.lower()} {loc.lower()} "
            f"{city.lower()} {state.lower()} pin - {pin[:3]} {pin[3:]}   ph: +91 {phone} ", [VERIFIED], b)
        name, phone, flat, building, street = _person(rng)
        add("WhatsApp multi-line, all correct",
            f"Name: {name}\nMobile: {phone}\nAddress: {flat}, {building}\n{street}, {loc}\n{city} - {pin}\n{state}",
            [VERIFIED], b)
        name, phone, flat, building, street = _person(rng)
        typo = _city_typo(city, rng)
        add("City misspelt", f"{name}, {flat}, {building}, {street}, {loc}, {typo}, {state}, {pin}, {phone}",
            [NCC], b, expect_correction={"city": city})
        name, phone, flat, building, street = _person(rng)
        add("State misspelt",
            f"{name}, {flat}, {building}, {street}, {loc}, {city}, {STATE_TYPOS.get(state) or state[:-1]}, {pin}, {phone}",
            [NCC], b, expect_correction={"state": state})
        name, phone, flat, building, street = _person(rng)
        add("Phone missing", f"{name}, {flat}, {building}, {street}, {loc}, {city}, {state}, {pin}", [NCC], b)
        name, phone, *_ = _person(rng)
        add("House number and street missing", f"{name}, {loc}, {city}, {state}, {pin}, {phone}", [NCC], b)
        name, phone, flat, building, street = _person(rng)
        wrong = _other_state_pin(con, state, rng)
        add("PIN from another state", f"{name}, {flat}, {building}, {street}, {loc}, {city}, {state}, {wrong}, {phone}",
            [WARNING], b, wrong_pin=wrong)
        name, phone, flat, building, street = _person(rng)
        near = _near_miss_pin(con, b, offices_by_state)
        if near:
            add("Near-miss PIN (same state, 15-60 km away)",
                f"{name}, {flat}, {building}, {street}, {loc}, {city}, {state}, {near}, {phone}",
                [NCC, WARNING], b, wrong_pin=near)
        else:
            add("Near-miss PIN (same state, 15-60 km away)", "", [], b, skipped="no PIN 15-60 km away")
    for text in GARBAGE:
        add("Not an address", text, [FAILED])

    cases = [c for c in cases if not c.get("skipped")]
    path.write_text(json.dumps({"seed": seed, "cases": cases}, indent=2, ensure_ascii=False), encoding="utf-8")
    return cases


if __name__ == "__main__":
    # Optional: a different seed builds an independent holdout set.
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    path = DATASET if seed == SEED else DATASET.with_name(f"messy_250_holdout_{seed}.json")
    built = build(seed, path)
    print(f"{len(built)} cases -> {path}")
