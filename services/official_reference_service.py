"""Whole-India postal and administrative reference layer.

Primary local sources bundled with this project:
- India Post all-India pincode directory CSV.
- LGD all-India village directory CSV.
- India postal ↔ LGD state/district mapping CSV.

A SQLite index is built once from the CSVs so 165k+ postal rows and 680k+ village
rows can be queried quickly without loading the entire datasets into Python objects.
The raw CSVs remain in data/ as the traceable source data.
"""
from __future__ import annotations

import difflib
from functools import lru_cache
import gzip
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.live_postal_service import (
    lookup_pincode as live_lookup_pincode,
    search as live_postal_search,
    health as live_postal_health,
)

logger = logging.getLogger("addressguard.reference")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_PINCODE_CSV = DATA_DIR / "india_post_pincode.csv"
DEFAULT_VILLAGES_CSV = DATA_DIR / "lgd_villages.csv"
DEFAULT_MAPPING_CSV = DATA_DIR / "postal_lgd_mapping.csv"
DEFAULT_DB = DATA_DIR / "reference_index.sqlite3"
# Optional extras downloaded by scripts/fetch_reference_data.py.
OPTIONAL_INPUTS = (DATA_DIR / "lgd_pincode_villages.csv", DATA_DIR / "osm_localities.csv")

_STATE_ALIASES = {
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "jammu and kashmir": "Jammu and Kashmir",
    "jammu & kashmir": "Jammu and Kashmir",
    "nct of delhi": "Delhi",
    "delhi": "Delhi",
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "telengana": "Telangana",
    "telingana": "Telangana",
    "karnatak": "Karnataka",
    "maharastra": "Maharashtra",
    "kerela": "Kerala",
    "rajasthan": "Rajasthan",
}

_WORD_RE = re.compile(r"[^a-z0-9]+")
_DB_READY = False


def _norm(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(_WORD_RE.sub(" ", s).split())


def _canon_state(value: Any) -> str:
    raw = " ".join(str(value or "").strip().split())
    return _STATE_ALIASES.get(raw.lower(), raw)


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _digits(v: Any) -> str:
    return re.sub(r"\D", "", _clean(v))[:6]


def _paths() -> tuple[Path, Path, Path, Path]:
    pin = Path(os.getenv("INDIA_POST_PINCODE_CSV", str(DEFAULT_PINCODE_CSV)))
    villages = Path(os.getenv("LGD_VILLAGES_CSV", str(DEFAULT_VILLAGES_CSV)))
    mapping = Path(os.getenv("POSTAL_LGD_MAPPING_CSV", str(DEFAULT_MAPPING_CSV)))
    db = Path(os.getenv("REFERENCE_INDEX_DB", str(DEFAULT_DB)))
    for p_name, p in (("pin", pin), ("villages", villages), ("mapping", mapping), ("db", db)):
        if not p.is_absolute():
            p = BASE_DIR / p
        if p_name == "pin": pin = p
        elif p_name == "villages": villages = p
        elif p_name == "mapping": mapping = p
        else: db = p
    return pin, villages, mapping, db


def _index_compatible(db: Path) -> bool:
    """Return True only when the SQLite file has the schema this service expects.

    This prevents an unrelated/older SQLite cache from being accepted merely
    because its timestamp is newer than the CSV snapshots.
    """
    try:
        with sqlite3.connect(db, timeout=10) as con:
            tables = {
                str(r[0])
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not {"postal_offices", "villages", "pin_lgd", "osm_localities"}.issubset(tables):
                return False
            village_columns = {str(r[1]) for r in con.execute("PRAGMA table_info(villages)").fetchall()}
            return "pincodes" in village_columns
    except Exception:
        return False


PACKAGED_INDEX = DATA_DIR / "reference_index.sqlite3.gz"
_PACKAGED_LOCK = threading.Lock()
_PACKAGED_DB: Path | None = None


def _packaged_index(db: Path) -> Path | None:
    """Use a ready-built index when the raw CSVs are not deployed.

    Serverless hosts (Vercel) ship only data/reference_index.sqlite3.gz, built
    by scripts/package_reference_index.py, and have a read-only project folder.
    The archive is unpacked once per instance into the writable temp folder.
    """
    global _PACKAGED_DB
    if db.exists() and _index_compatible(db):
        return db
    if not PACKAGED_INDEX.exists():
        return None
    with _PACKAGED_LOCK:
        if _PACKAGED_DB is not None:
            return _PACKAGED_DB
        target = Path(os.getenv("REFERENCE_INDEX_CACHE_DIR", tempfile.gettempdir())) / "addressguard_reference_index.sqlite3"
        if not (target.exists() and _index_compatible(target)):
            partial = target.with_suffix(f".{os.getpid()}.partial")
            with gzip.open(PACKAGED_INDEX, "rb") as src, open(partial, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            os.replace(partial, target)
            logger.info("Unpacked packaged reference index to %s", target)
        _PACKAGED_DB = target
        return target


def _ensure_index() -> Path:
    global _DB_READY
    pin, villages, mapping, db = _paths()
    if not (pin.exists() and mapping.exists()):
        packaged = _packaged_index(db)
        if packaged:
            return packaged
        missing = [str(p) for p in (pin, mapping) if not p.exists()]
        raise FileNotFoundError("Missing reference dataset(s): " + ", ".join(missing))
    if not villages.exists() and not _DB_READY:
        logger.warning("LGD villages dataset missing (%s); village lookups disabled", villages)

    newest_input = max(p.stat().st_mtime for p in (pin, villages, mapping, *OPTIONAL_INPUTS) if p.exists())
    compatible = db.exists() and _index_compatible(db)
    if _DB_READY and compatible and db.stat().st_mtime >= newest_input:
        return db
    if compatible and db.stat().st_mtime >= newest_input:
        _DB_READY = True
        return db

    logger.info("Building reference index from whole-India CSV datasets...")
    script = BASE_DIR / "scripts" / "build_reference_index.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=int(os.getenv("REFERENCE_INDEX_BUILD_TIMEOUT", "180")),
    )
    if proc.returncode != 0:
        logger.error("Reference index build failed: %s", proc.stderr[-4000:])
        raise RuntimeError("Reference index build failed")
    _DB_READY = True
    logger.info("Reference index ready: %s", db)
    return db


def _connect() -> sqlite3.Connection:
    db = _ensure_index()
    con = sqlite3.connect(db, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def reset_cache() -> None:
    global _DB_READY, _REFERENCE_STATUS_CACHE
    _DB_READY = False
    _REFERENCE_STATUS_CACHE = None


def _row_dict(row: sqlite3.Row) -> dict[str, str]:
    return {k: ("" if v is None else str(v)) for k, v in zip(row.keys(), row)}


def _postal_out(row: sqlite3.Row) -> dict[str, str]:
    return {
        "source": "India Post dataset",
        "kind": "post_office",
        "name": row["officename"],
        "pincode": row["pincode"],
        "office_type": row["officetype"],
        "delivery_status": row["delivery"],
        "taluk": row["taluk"],
        "district": row["district"],
        "state": _canon_state(row["statename"]),
        "division": row["divisionname"],
        "region": row["regionname"],
        "circle": row["circlename"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
    }


def _village_out(row: sqlite3.Row) -> dict[str, str]:
    return {
        "source": "LGD village dataset",
        "kind": "village",
        "name": row["village_name"],
        "pincode": "",
        "office_type": "",
        "delivery_status": "",
        "taluk": row["subdistrict_name"],
        "district": row["district_name"],
        "state": _canon_state(row["state_name"]),
        "division": "",
        "region": "",
        "circle": "",
        "latitude": "",
        "longitude": "",
        "village_code": row["village_code"],
        "subdistrict_code": row["subdistrict_code"],
        "district_code": row["district_code"],
        "block": row["block_name"],
        # LGD village-to-PIN links (empty when that optional file is absent).
        "pincodes": [p for p in str(row["pincodes"] if "pincodes" in row.keys() else "").split(",") if p],
    }


def _osm_out(row: sqlite3.Row) -> dict[str, str]:
    return {
        "source": "OpenStreetMap locality (ODbL)",
        "kind": "osm_locality",
        "name": row["name"],
        "pincode": row["pincode"] or "",
        "office_type": "",
        "delivery_status": "",
        "taluk": "",
        "district": row["district"],
        "state": _canon_state(row["state"]),
        "division": "",
        "region": "",
        "circle": "",
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "place": row["place"],
    }


def _mapping_rows(con: sqlite3.Connection, pin: str) -> list[dict[str, str]]:
    rows = con.execute(
        "SELECT * FROM pin_lgd WHERE pincode=? ORDER BY id LIMIT 50", (pin,)
    ).fetchall()
    return [_row_dict(r) for r in rows]


def lookup_pincode(pin: str) -> list[dict[str, str]]:
    pin = _digits(pin)
    if len(pin) != 6:
        return []

    # Local whole-India India Post snapshot is authoritative within this app.
    try:
        with _connect() as con:
            rows = con.execute(
                "SELECT * FROM postal_offices WHERE pincode=? ORDER BY officename", (pin,)
            ).fetchall()
            if rows:
                return [_postal_out(r) for r in rows]
    except Exception as exc:
        logger.warning("Local India Post lookup failed for %s: %s", pin, exc)

    # Optional live fallback for a PIN not present in the local snapshot.
    live_rows, _meta = live_lookup_pincode(pin)
    return [
        {
            "source": "Live postal API (India Post-derived)",
            "kind": "post_office",
            "name": _clean(r.get("office_name") or r.get("name")),
            "pincode": _digits(r.get("pincode") or r.get("pin_code")),
            "office_type": _clean(r.get("office_type") or r.get("branch_type")),
            "delivery_status": _clean(r.get("delivery_status")),
            "taluk": _clean(r.get("taluk") or r.get("subdistrict") or r.get("block")),
            "district": _clean(r.get("district") or r.get("district_name")),
            "state": _canon_state(r.get("state") or r.get("state_name")),
            "division": _clean(r.get("division")),
            "region": _clean(r.get("region")),
            "circle": _clean(r.get("circle")),
            "latitude": _clean(r.get("latitude") or r.get("lat")),
            "longitude": _clean(r.get("longitude") or r.get("lon") or r.get("lng")),
        }
        for r in live_rows
    ]


_REFERENCE_STATUS_CACHE: dict[str, Any] | None = None


def get_reference_status() -> dict[str, Any]:
    """Return dataset/index status. Only a successful status is cached, so a
    transient index failure is re-checked on the next call instead of being
    remembered until restart."""
    global _REFERENCE_STATUS_CACHE
    if _REFERENCE_STATUS_CACHE is not None:
        return dict(_REFERENCE_STATUS_CACHE)
    pin, villages, mapping, db = _paths()
    status: dict[str, Any] = {
        "india_post_file": pin.exists(),
        "lgd_villages_file": villages.exists(),
        "postal_lgd_mapping_file": mapping.exists(),
        "reference_index": False,
        "india_post_rows": 0,
        "lgd_village_rows": 0,
        "postal_lgd_mapping_rows": 0,
        "distinct_pincodes": 0,
        "distinct_states": 0,
        "paths": {
            "india_post": str(pin),
            "lgd_villages": str(villages),
            "postal_lgd_mapping": str(mapping),
            "index": str(db),
        },
        "live_postal_api": get_live_reference_status() if os.getenv("REFERENCE_STATUS_CHECK_LIVE", "false").strip().lower() in {"1", "true", "yes", "on"} else {"enabled": bool(os.getenv("LIVE_POSTAL_API_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}), "status": "NOT_CHECKED"},
    }
    try:
        with _connect() as con:
            status["reference_index"] = True
            status["india_post_rows"] = con.execute("SELECT count(*) FROM postal_offices").fetchone()[0]
            status["lgd_village_rows"] = con.execute("SELECT count(*) FROM villages").fetchone()[0]
            status["postal_lgd_mapping_rows"] = con.execute("SELECT count(*) FROM pin_lgd").fetchone()[0]
            try:
                status["osm_locality_rows"] = con.execute("SELECT count(*) FROM osm_localities").fetchone()[0]
                status["lgd_villages_with_pin"] = con.execute("SELECT count(*) FROM villages WHERE pincodes<>''").fetchone()[0]
            except sqlite3.OperationalError:
                status["osm_locality_rows"] = 0
                status["lgd_villages_with_pin"] = 0
            status["distinct_pincodes"] = con.execute("SELECT count(DISTINCT pincode) FROM postal_offices").fetchone()[0]
            status["distinct_states"] = con.execute("SELECT count(DISTINCT norm_state) FROM postal_offices").fetchone()[0]
    except Exception as exc:
        status["error"] = type(exc).__name__
        return status
    _REFERENCE_STATUS_CACHE = dict(status)
    return status


def _ref_name(value: Any) -> str:
    value = _norm(value)
    # Keep reference matching consistent with the SQLite builder: postal-office
    # qualifiers such as "Indiranagar S.O (Bengaluru)" are display metadata,
    # not part of the locality name. Remove parenthetical qualifiers before
    # stripping S.O/B.O/H.O/D.O suffixes so an exact user value is not shown as
    # a false spelling correction.
    value = re.sub(r"\s*\([^)]*\)", "", value)
    return re.sub(r"\s(?:s|b|h|d) ?o$", "", value).strip()


def _similar(a: Any, b: Any, threshold: float = 0.78) -> bool:
    a, b = _ref_name(a), _ref_name(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _display_place_name(value: Any) -> str:
    s = _clean(value)
    # Remove postal-office display qualifiers before stripping the office-type
    # suffix. This keeps suggestions human-readable and prevents source labels
    # such as "Indiranagar S.O (Bengaluru)" from leaking into corrections.
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r"\s+(?:s\.?o\.?|b\.?o\.?|h\.?o\.?|d\.?o\.?)$", "", s, flags=re.I)
    # The supplied reference files contain some administrative names in all
    # caps. Suggestions should remain human-readable while preserving normal
    # words from mixed-case source rows.
    if s.isupper():
        s = s.title()
    return s.strip()


@lru_cache(maxsize=4096)
def is_state_known(state: str) -> bool:
    target = _norm(_canon_state(state))
    if not target:
        return False
    try:
        with _connect() as con:
            return bool(con.execute("SELECT 1 FROM postal_offices WHERE norm_state=? LIMIT 1", (target,)).fetchone() or
                        con.execute("SELECT 1 FROM villages WHERE norm_state=? LIMIT 1", (target,)).fetchone())
    except Exception:
        return False


@lru_cache(maxsize=4096)
def district_state_matches(district: str, state: str) -> bool:
    nd, ns = _norm(district), _norm(_canon_state(state))
    if not nd or not ns:
        return False
    try:
        with _connect() as con:
            if con.execute("SELECT 1 FROM pin_lgd WHERE norm_district=? AND norm_state=? LIMIT 1", (nd, ns)).fetchone():
                return True
            return bool(con.execute("SELECT 1 FROM villages WHERE norm_district=? AND norm_state=? LIMIT 1", (nd, ns)).fetchone())
    except Exception:
        return False


@lru_cache(maxsize=4096)
def subdistrict_context_matches(name: str, district: str = "", state: str = "") -> bool:
    nn, nd, ns = _norm(name), _norm(district), _norm(_canon_state(state))
    if not nn:
        return False
    try:
        with _connect() as con:
            sql = "SELECT 1 FROM villages WHERE norm_subdistrict=?"
            params: list[str] = [nn]
            if nd:
                sql += " AND norm_district=?"; params.append(nd)
            if ns:
                sql += " AND norm_state=?"; params.append(ns)
            return bool(con.execute(sql + " LIMIT 1", params).fetchone())
    except Exception:
        return False


def _postal_pin_context(con: sqlite3.Connection, pin: str) -> tuple[set[str], set[str]]:
    if not pin:
        return set(), set()
    rows = con.execute("SELECT DISTINCT norm_state,norm_district FROM postal_offices WHERE pincode=?", (pin,)).fetchall()
    return ({r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]})


def _context_score(item: dict[str, str], city: str, district: str, state: str, pin: str, pin_states: set[str], pin_districts: set[str]) -> tuple[int, dict[str, bool]]:
    score = 0
    evidence = {"pin": False, "state": False, "district": False, "city": False, "administrative": False}
    ni_state = _norm(_canon_state(item.get("state", ""))); ni_district = _norm(item.get("district", "")); ni_taluk = _norm(item.get("taluk", ""))
    if pin and ((item.get("pincode") and item.get("pincode") == pin) or pin in (item.get("pincodes") or [])):
        score += 55; evidence["pin"] = True
    if state and ni_state == _norm(_canon_state(state)):
        score += 20; evidence["state"] = True
    if district and ni_district == _norm(district):
        score += 15; evidence["district"] = True
    if city and (_similar(item.get("taluk"), city) or _similar(item.get("district"), city)):
        score += 8; evidence["city"] = True
    # Without a direct village-to-PIN link, the PIN's district/state is only
    # supporting evidence, never proof that the village belongs to that PIN.
    if item.get("kind") == "village" and pin and not evidence["pin"]:
        if ni_state and ni_state in pin_states:
            score += 12; evidence["administrative"] = True
        if ni_district and ni_district in pin_districts:
            score += 12; evidence["administrative"] = True
    return score, evidence


@lru_cache(maxsize=8192)
def reference_place_name(name: str, state: str = "") -> bool:
    """True when name exactly matches a post office, OSM locality or LGD village
    (within the given state, when one is supplied). Used by the parser to tell
    a locality apart from a street or unrecognised text."""
    target = _norm(name)
    if not target or re.search(r"\d", target) or len(target.split()) > 5:
        return False
    ns = _norm(_canon_state(state))
    try:
        with _connect() as con:
            for table, column in (("postal_offices", "norm_name"), ("osm_localities", "norm_name"), ("villages", "norm_village")):
                sql = f"SELECT 1 FROM {table} WHERE {column}=?"
                params = [target]
                if ns:
                    sql += " AND norm_state=?"
                    params.append(ns)
                try:
                    if con.execute(sql + " LIMIT 1", params).fetchone():
                        return True
                except sqlite3.OperationalError:
                    continue
    except Exception as exc:
        logger.warning("Reference place lookup failed: %s", type(exc).__name__)
    return False


def _osm_in_pin_district(item: dict[str, Any], pin_districts: set[str]) -> bool:
    return bool(item.get("district")) and _norm(item.get("district")) in pin_districts


def _fuzzy_rows(con: sqlite3.Connection, table: str, name_col: str, norm_col: str, target: str, district: str, state: str, limit: int = 5000) -> list[sqlite3.Row]:
    first = target[:1]
    lo, hi = max(1, len(target) - 2), len(target) + 3
    if table == "villages":
        sql = f"SELECT * FROM {table} WHERE substr({norm_col},1,1)=? AND length({norm_col}) BETWEEN ? AND ?"
    else:
        sql = f"SELECT * FROM {table} WHERE substr({norm_col},1,1)=? AND length({norm_col}) BETWEEN ? AND ?"
    params: list[str | int] = [first, lo, hi]
    nd, ns = _norm(district), _norm(_canon_state(state))
    if nd:
        sql += " AND norm_district=?"; params.append(nd)
    if ns:
        sql += " AND norm_state=?"; params.append(ns)
    sql += f" LIMIT {int(limit)}"
    return con.execute(sql, params).fetchall()


def _candidate_rows(con: sqlite3.Connection, locality: str, city: str, district: str, state: str, pin: str) -> list[dict[str, str]]:
    target = _ref_name(locality)
    results: list[dict[str, str]] = []
    pin_states, pin_districts = _postal_pin_context(con, pin)

    # Exact LGD village names.
    village_sql = "SELECT * FROM villages WHERE norm_village=?"
    params: list[str] = [target]
    if district:
        village_sql += " AND norm_district=?"; params.append(_norm(district))
    if state:
        village_sql += " AND norm_state=?"; params.append(_norm(_canon_state(state)))
    village_rows = con.execute(village_sql + " LIMIT 30", params).fetchall()
    for row in village_rows:
        item = _village_out(row)
        sim = 1.0
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": sim, "context_score": score, "evidence": evidence, "match_type": "exact_village"})
        results.append(item)

    # Exact postal office names (suffix S.O/B.O/H.O stripped for comparison).
    post_rows = con.execute("SELECT * FROM postal_offices WHERE norm_name=? LIMIT 30", (target,)).fetchall()
    for row in post_rows:
        item = _postal_out(row)
        sim = 1.0
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": sim, "context_score": score, "evidence": evidence, "match_type": "exact_post_office"})
        results.append(item)

    # Exact OpenStreetMap urban localities (suburbs, neighbourhoods, quarters).
    osm_sql = "SELECT * FROM osm_localities WHERE norm_name=?"
    osm_params: list[str] = [target]
    if state:
        osm_sql += " AND (norm_state=? OR norm_state='')"
        osm_params.append(_norm(_canon_state(state)))
    try:
        osm_rows = con.execute(osm_sql + " LIMIT 30", osm_params).fetchall()
    except sqlite3.OperationalError:
        osm_rows = []  # index built before OSM support; rebuilt on next start
    for row in osm_rows:
        item = _osm_out(row)
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": 1.0, "context_score": score, "evidence": evidence, "match_type": "exact_osm_locality"})
        results.append(item)

    if results:
        return results

    # Fuzzy LGD village candidates.
    for row in _fuzzy_rows(con, "villages", "village_name", "norm_village", target, district, state):
        item = _village_out(row)
        cand = _ref_name(item["name"])
        sim = difflib.SequenceMatcher(None, cand, target).ratio()
        if sim < 0.72:
            continue
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": sim, "context_score": score, "evidence": evidence, "match_type": "fuzzy_village"})
        results.append(item)

    # Fuzzy postal office candidates.
    for row in _fuzzy_rows(con, "postal_offices", "officename", "norm_name", target, district, state):
        item = _postal_out(row)
        cand = _ref_name(item["name"])
        sim = difflib.SequenceMatcher(None, cand, target).ratio()
        if sim < 0.72:
            continue
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": sim, "context_score": score, "evidence": evidence, "match_type": "fuzzy_post_office"})
        results.append(item)

    # Fuzzy OpenStreetMap locality candidates.
    try:
        osm_fuzzy = _fuzzy_rows(con, "osm_localities", "name", "norm_name", target, district, state)
    except sqlite3.OperationalError:
        osm_fuzzy = []
    for row in osm_fuzzy:
        item = _osm_out(row)
        sim = difflib.SequenceMatcher(None, _ref_name(item["name"]), target).ratio()
        if sim < 0.72:
            continue
        score, evidence = _context_score(item, city, district, state, pin, pin_states, pin_districts)
        item.update({"similarity": sim, "context_score": score, "evidence": evidence, "match_type": "fuzzy_osm_locality"})
        results.append(item)
    return results


@lru_cache(maxsize=4096)
def locality_matches(locality: str, city: str = "", district: str = "", state: str = "", pin: str = "") -> dict[str, Any]:
    target = _ref_name(locality)
    if not target:
        return {"verified": False, "candidates": [], "reason": "Locality missing", "source": "reference data"}

    try:
        with _connect() as con:
            candidates = _candidate_rows(con, locality, city, district, state, _digits(pin))
            _, pin_districts = _postal_pin_context(con, _digits(pin))
            candidates.sort(key=lambda x: (-int(x.get("context_score", 0)), -float(x.get("similarity", 0)), x.get("name", "")))
            out: list[dict[str, Any]] = []
            seen = set()
            for item in candidates[:10]:
                key = (_norm(item.get("name")), item.get("kind"), item.get("district"), item.get("state"), item.get("pincode"))
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)

            verified = False
            strong = None
            if out:
                best = out[0]
                exact_name = float(best.get("similarity", 0)) >= 0.999
                ev = best.get("evidence", {}) or {}
                if best.get("kind") == "post_office":
                    verified = exact_name and (ev.get("pin") or (ev.get("state") and (ev.get("district") or ev.get("city"))))
                elif best.get("kind") == "osm_locality":
                    # OSM district/state come from the nearest post office, so
                    # require the supplied PIN's district (or a direct postcode
                    # match) to agree, not the state alone.
                    verified = exact_name and (ev.get("pin") or (ev.get("state") and (
                        ev.get("district") or ev.get("city") or _osm_in_pin_district(best, pin_districts))))
                else:
                    # LGD villages: a direct village-to-PIN link is the strongest
                    # proof; otherwise district/state administrative context.
                    verified = exact_name and (ev.get("pin") or ev.get("district") or ev.get("state") or ev.get("administrative"))
                if not verified and float(best.get("similarity", 0)) >= 0.90 and int(best.get("context_score", 0)) >= 35:
                    strong = best

            return {
                "verified": bool(verified),
                "strong_candidate": strong,
                "candidates": out,
                "reason": "Exact locality/post-office match supported by postal or LGD administrative context" if verified else "High-confidence locality candidate found" if strong else "No sufficiently supported locality match",
                "source": "India Post CSV + LGD village CSV + postal-LGD mapping CSV",
            }
    except Exception as exc:
        logger.warning("Reference locality lookup failed: %s", exc)
        # Last-resort live postal search, if enabled.
        rows: list[dict[str, str]] = []
        for q in [str(locality).strip(), f"{str(locality).strip()} {str(city).strip()}".strip()] if city else [str(locality).strip()]:
            live_rows, _meta = live_postal_search(q, limit=20)
            rows.extend({
                "source": "Live postal API (India Post-derived)",
                "kind": "post_office",
                "name": _clean(r.get("office_name") or r.get("name")),
                "pincode": _digits(r.get("pincode") or r.get("pin_code")),
                "district": _clean(r.get("district") or r.get("district_name")),
                "state": _canon_state(r.get("state") or r.get("state_name")),
                "taluk": _clean(r.get("taluk") or r.get("subdistrict") or r.get("block")),
            } for r in live_rows)
        return {"verified": False, "strong_candidate": None, "candidates": rows[:10], "reason": "Local reference index unavailable; live postal fallback used", "source": "live postal API"}


def _fuzzy_reference_names(con: sqlite3.Connection, field: str, target: str, city: str = "", district: str = "", state: str = "", pin: str = "") -> list[dict[str, Any]]:
    """Find whole-India reference candidates without loading the full index.

    The old implementation fetched thousands of rows and then fuzzy-compared
    them in Python for every validation. This version uses indexed/cheap
    prefix+length filtering first, then fuzzy matching only on a small
    candidate pool. Geographic context remains the final ranking signal.
    """
    target_n = _ref_name(target)
    if not target_n:
        return []
    nd, ns, np = _norm(district), _norm(_canon_state(state)), _digits(pin)
    first = target_n[:1]
    lo, hi = max(1, len(target_n) - 2), len(target_n) + 3

    def fetch(table, name_col, norm_col, extra="", params=()):
        sql = f"SELECT DISTINCT {name_col} AS name, {norm_col} AS norm_name, norm_district, norm_state FROM {table} WHERE {name_col}<>'' AND substr({norm_col},1,1)=? AND length({norm_col}) BETWEEN ? AND ?"
        p = [first, lo, hi]
        if extra:
            sql += " AND " + extra
            p.extend(params)
        sql += " LIMIT 5000"
        return con.execute(sql, p).fetchall()

    rows = []
    if field == "state":
        sql = "SELECT DISTINCT state_name AS name, norm_state AS norm_name FROM villages WHERE state_name<>'' AND substr(norm_state,1,1)=? AND length(norm_state) BETWEEN ? AND ? LIMIT 500"
        rows = con.execute(sql, [first, lo, hi]).fetchall()
        if not rows:
            sql = "SELECT DISTINCT statename AS name, norm_state AS norm_name FROM postal_offices WHERE statename<>'' AND substr(norm_state,1,1)=? AND length(norm_state) BETWEEN ? AND ? LIMIT 500"
            rows = con.execute(sql, [first, lo, hi]).fetchall()
    elif field == "district":
        extra = "norm_state=?" if ns else ""
        rows = fetch("villages", "district_name", "norm_district", extra, [ns] if ns else ())
    elif field == "city":
        extra = []
        params = []
        if ns:
            extra.append("norm_state=?"); params.append(ns)
        if nd:
            extra.append("norm_district=?"); params.append(nd)
        where = " AND ".join(extra)
        rows = fetch("postal_offices", "taluk", "norm_taluk", where, params)
        rows += fetch("villages", "subdistrict_name", "norm_subdistrict", where, params)
        rows += fetch("villages", "district_name", "norm_district", where, params)
    else:
        return []

    best = []
    seen = set()
    pin_states, pin_districts = _postal_pin_context(con, np) if np and field in {"district", "city"} else (set(), set())
    for row in rows:
        name = _clean(row["name"])
        norm_name = _ref_name(name)
        if not name or norm_name in seen:
            continue
        seen.add(norm_name)
        sim = difflib.SequenceMatcher(None, target_n, norm_name).ratio()
        if sim < 0.84:
            continue
        context = 0
        if np and field in {"district", "city"}:
            row_state = row["norm_state"] if "norm_state" in row.keys() else ""
            row_dist = row["norm_district"] if "norm_district" in row.keys() else ""
            if row_state and row_state in pin_states: context += 15
            if row_dist and row_dist in pin_districts: context += 20
        if ns and "norm_state" in row.keys() and row["norm_state"] == ns: context += 15
        if nd and "norm_district" in row.keys() and row["norm_district"] == nd: context += 20
        best.append((sim + context / 1000.0, sim, context, name))

    best.sort(reverse=True)
    return [{"name": name, "similarity": sim, "context_score": context} for _rank, sim, context, name in best[:10]]

@lru_cache(maxsize=8192)
def generate_reference_correction(field: str, value: str, city: str = "", district: str = "", state: str = "", pin: str = "") -> dict[str, Any] | None:
    """Generate a spelling suggestion from the complete supplied reference index.

    This complements the legacy aliases and the locality-specific matcher.
    It never silently changes the address.
    """
    field = str(field or "").strip().lower()
    value = _clean(value)
    if not value or field not in {"state", "district", "city", "locality"}:
        return None
    try:
        if field == "locality":
            return generate_official_correction(value, city=city, district=district, state=state, pin=pin)
        with _connect() as con:
            candidates = _fuzzy_reference_names(con, field, value, city, district, state, pin)
        if not candidates:
            return None
        best = candidates[0]
        suggested = _display_place_name(best["name"])
        if not suggested or _ref_name(suggested) == _ref_name(value):
            return None
        # Require both a strong textual match and enough contextual support
        # for district/city; states need only the strong name match.
        threshold = 0.86 if field == "state" else 0.90
        if best["similarity"] < threshold:
            return None
        if field in {"city", "district"} and (city or district or state or pin) and best["context_score"] < 15:
            return None
        confidence = min(98, max(84, round(best["similarity"] * 100 + min(8, best["context_score"] / 4))))
        return {
            "field": field,
            "original": value,
            "suggested": suggested,
            "reason": f"{field.title()} matched against whole-India reference index with contextual geographic evidence",
            "confidence": confidence,
            "reference_source": "India Post + LGD + postal-LGD SQLite index",
        }
    except Exception as exc:
        logger.warning("Reference correction failed for %s=%s: %s", field, value, exc)
        return None


@lru_cache(maxsize=8192)
def generate_official_correction(locality: str, city: str = "", district: str = "", state: str = "", pin: str = "") -> dict[str, Any] | None:
    result = locality_matches(locality, city=city, district=district, state=state, pin=pin)
    candidate = result.get("strong_candidate")
    if not candidate:
        # Allow a fuzzy candidate at >= 0.90 with adequate context when the UI needs a correction.
        candidates = result.get("candidates") or []
        for c in candidates:
            if float(c.get("similarity", 0)) >= 0.90 and int(c.get("context_score", 0)) >= 35:
                candidate = c; break
    if not candidate:
        return None
    original = str(locality or "").strip()
    suggested = _display_place_name(candidate.get("name"))
    if not original or not suggested or _ref_name(original) == _ref_name(suggested):
        return None
    confidence = min(97, max(82, round(float(candidate.get("similarity", 0.9)) * 100)))
    return {
        "field": "locality",
        "original": original,
        "suggested": suggested,
        "reason": f"Matched against {candidate.get('source', 'reference data')} with geographic context",
        "confidence": confidence,
        "source": candidate.get("source", "reference data"),
    }


def _km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(lat2 - lat1, dx) * 111.2


def _coords(item: Any) -> tuple[float, float] | None:
    try:
        lat, lon = float(item["latitude"]), float(item["longitude"])
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return (lat, lon) if lat and lon else None


def _in_area(area: list[str], row_district: Any, row_taluk: Any = "") -> bool:
    return not area or any(_similar(row_district, a) or _similar(row_taluk, a) for a in area)


CITY_AREA_KM = 25.0


@lru_cache(maxsize=4096)
def pin_within_city_area(pin: str, city_names: tuple[str, ...], state: str) -> bool:
    """True when a post office of ``pin`` lies within CITY_AREA_KM of a post
    office named after, or in a district named after, the city.

    Large cities span several districts (Hyderabad: Hyderabad, Ranga Reddy,
    Medchal-Malkajgiri), so a district-name comparison alone rejects real
    suburbs such as Peerzadiguda.
    """
    pin, state_key = _digits(pin), _norm(_canon_state(state))
    names = [n for n in (_norm(c) for c in city_names) if n]
    if len(pin) != 6 or not names or not state_key:
        return False
    try:
        with _connect() as con:
            pin_points = [p for p in (_coords(r) for r in con.execute(
                "SELECT latitude, longitude FROM postal_offices WHERE pincode=?", (pin,)).fetchall()) if p]
            if not pin_points:
                return False
            clauses = " OR ".join(["norm_district LIKE ? OR norm_name=? OR norm_taluk=?"] * len(names))
            params = [x for n in names for x in (f"{n}%", n, n)]
            city_points = [p for p in (_coords(r) for r in con.execute(
                f"SELECT latitude, longitude FROM postal_offices WHERE norm_state=? AND ({clauses})",
                (state_key, *params)).fetchall()) if p]
    except Exception as exc:
        logger.warning("City-area check failed for %s: %s", pin, exc)
        return False
    return any(_km_between(*a, *b) <= CITY_AREA_KM for a in pin_points for b in city_points)


# Thresholds calibrated on OpenStreetMap localities that carry their own PIN:
# 90% lie within 5 km of a post office of that PIN.
NEAR_MISS_PIN_KM = 10.0
NEARBY_OTHER_PIN_KM = 2.0


@lru_cache(maxsize=4096)
def check_pin_near_locality(locality: str, city: str = "", district: str = "", state: str = "", pin: str = "") -> dict[str, Any] | None:
    """Compare where the locality is with where the PIN's post offices are.

    Returns {"status": "NEAR"} or {"status": "DISTANT", ...}, or None when the
    data cannot judge it (locality location unknown or ambiguous, no office
    coordinates). DISTANT needs both a far PIN and a post office of another
    PIN right next to the locality, because office coordinates contain errors.
    """
    pin = _digits(pin)
    target, state_key = _ref_name(locality), _norm(_canon_state(state))
    if len(pin) != 6 or not target or not state_key:
        return None
    area = [v for v in (district, city) if _clean(v)]
    try:
        with _connect() as con:
            pin_offices = con.execute(
                "SELECT officename, norm_name, latitude, longitude FROM postal_offices WHERE pincode=?", (pin,)
            ).fetchall()
            if any(r["norm_name"] == target for r in pin_offices):
                return {"status": "NEAR", "distance_km": 0.0}
            pin_points = [p for p in (_coords(r) for r in pin_offices) if p]
            # OpenStreetMap locality points are preferred: India Post office
            # coordinates are sometimes several kilometres off.
            points = []
            for sql in (
                "SELECT district, '' AS taluk, latitude, longitude FROM osm_localities WHERE norm_name=? AND norm_state=?",
                "SELECT district, taluk, latitude, longitude FROM postal_offices WHERE norm_name=? AND norm_state=?",
            ):
                points = [
                    p for p in (
                        _coords(r) for r in con.execute(sql, (target, state_key)).fetchall()
                        if _in_area(area, r["district"], r["taluk"])
                    ) if p
                ]
                if points:
                    break
            if not pin_points or not points:
                return None
            if max(_km_between(*a, *b) for a in points for b in points) > 5:
                return None  # same name in several places: location is ambiguous
            distance = min(_km_between(*a, *b) for a in points for b in pin_points)
            if distance <= NEAR_MISS_PIN_KM:
                return {"status": "NEAR", "distance_km": round(distance, 1)}
            lat, lon = points[0]
            box = NEARBY_OTHER_PIN_KM / 111.2 * 1.5
            nearby = []
            for r in con.execute(
                "SELECT officename, pincode, latitude, longitude FROM postal_offices WHERE norm_state=? AND pincode<>? "
                "AND CAST(latitude AS REAL) BETWEEN ? AND ? AND CAST(longitude AS REAL) BETWEEN ? AND ?",
                (state_key, pin, lat - box, lat + box, lon - box * 1.2, lon + box * 1.2),
            ).fetchall():
                point = _coords(r)
                if point and _km_between(lat, lon, *point) <= NEARBY_OTHER_PIN_KM:
                    nearby.append((_km_between(lat, lon, *point), r))
    except Exception as exc:
        logger.warning("PIN distance check failed for %s/%s: %s", locality, pin, exc)
        return None
    if not nearby:
        return None
    nearby.sort(key=lambda item: item[0])
    office = nearby[0][1]
    return {
        "status": "DISTANT",
        "distance_km": round(distance, 1),
        "nearby_pin": office["pincode"],
        "nearby_office": office["officename"],
    }


@lru_cache(maxsize=4096)
def suggest_pin_code(locality: str, city: str = "", district: str = "", state: str = "") -> dict[str, Any] | None:
    """Suggest the PIN code for a locality when the supplied PIN conflicts.

    Two sources, in order of strength:
    1. A post office with the locality's name in the same state and city/district,
       when all such offices share one PIN.
    2. The single OpenStreetMap location of the locality, matched to the nearest
       India Post office in the same district, only when that office is close and
       clearly nearer than any office with a different PIN.
    Ambiguous evidence yields no suggestion; a suggestion is never auto-applied.
    """
    target, state_key = _ref_name(locality), _norm(_canon_state(state))
    if not target or not state_key:
        return None
    area = [v for v in (district, city) if _clean(v)]

    def in_area(row_district: Any, row_taluk: Any = "") -> bool:
        return _in_area(area, row_district, row_taluk)

    try:
        with _connect() as con:
            offices = [
                r for r in con.execute(
                    "SELECT * FROM postal_offices WHERE norm_name=? AND norm_state=?", (target, state_key)
                ).fetchall()
                if in_area(r["district"], r["taluk"])
            ]
            pins = {r["pincode"] for r in offices}
            if len(pins) == 1:
                office = offices[0]
                return {
                    "field": "pin_code",
                    "suggested": office["pincode"],
                    "confidence": 90,
                    "reason": f"India Post office {office['officename']} ({office['district']}) serves "
                              f"{_clean(locality)} with PIN {office['pincode']}",
                    "source": "India Post dataset",
                }
            if pins:
                return None  # several offices of that name: ambiguous

            try:
                places = [
                    r for r in con.execute(
                        "SELECT * FROM osm_localities WHERE norm_name=? AND norm_state=?", (target, state_key)
                    ).fetchall()
                    if in_area(r["district"]) and _coords(r)
                ]
            except sqlite3.OperationalError:
                return None
            if len(places) != 1:
                return None
            place = places[0]
            if _digits(place["pincode"]) and len(_digits(place["pincode"])) == 6:
                return {
                    "field": "pin_code",
                    "suggested": _digits(place["pincode"]),
                    "confidence": 85,
                    "reason": f"OpenStreetMap records PIN {_digits(place['pincode'])} for {place['name']}",
                    "source": "OpenStreetMap locality (ODbL)",
                }
            lat, lon = _coords(place)
            nearby = []
            for r in con.execute(
                "SELECT officename, pincode, district, latitude, longitude FROM postal_offices "
                "WHERE norm_state=? AND norm_district=?", (state_key, place["norm_district"])
            ).fetchall():
                point = _coords(r)
                if point:
                    nearby.append((_km_between(lat, lon, *point), r))
    except Exception as exc:
        logger.warning("PIN suggestion failed for %s: %s", locality, exc)
        return None

    if not nearby:
        return None
    nearby.sort(key=lambda item: item[0])
    best_km, best = nearby[0]
    rival_km = next((km for km, r in nearby if r["pincode"] != best["pincode"]), None)
    if best_km > 1.5 or (rival_km is not None and rival_km < max(2 * best_km, best_km + 1.0)):
        return None
    return {
        "field": "pin_code",
        "suggested": best["pincode"],
        "confidence": 80,
        "reason": f"Nearest India Post office to {place['name']} ({place['district'].title()}) is "
                  f"{best['officename']}, {best_km:.1f} km away, PIN {best['pincode']}",
        "source": "OpenStreetMap locality + India Post dataset",
    }


def get_live_reference_status() -> dict[str, Any]:
    try:
        return live_postal_health()
    except Exception as exc:
        return {"enabled": False, "status": "ERROR", "error": type(exc).__name__}


def fetch_data_gov_records(api_key: str, resource_id: str, limit: int = 1000,
                           filters: dict[str, str] | None = None,
                           timeout: int = 20) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Optional data.gov.in fetcher retained for future official API sync."""
    if not api_key or not resource_id:
        raise ValueError("Both api_key and resource_id are required")
    all_records: list[dict[str, Any]] = []
    offset = 0
    total = None
    while True:
        params = {"api-key": api_key, "format": "json", "offset": str(offset), "limit": str(limit)}
        for key, value in (filters or {}).items():
            params[f"filters[{key}]"] = value
        url = "https://api.data.gov.in/resource/" + urllib.parse.quote(resource_id, safe="") + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AddressGuard-AI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not records:
            break
        all_records.extend(records)
        total = payload.get("total", total)
        offset += len(records)
        if len(all_records) >= int(total or 0) or len(records) < limit:
            break
    return all_records, {"total": total, "count": len(all_records)}
