#!/usr/bin/env python3
"""Download the optional reference datasets into data/.

    python scripts/fetch_reference_data.py            # both datasets
    python scripts/fetch_reference_data.py --lgd      # LGD villages + village PIN codes
    python scripts/fetch_reference_data.py --osm      # OpenStreetMap urban localities

Sources
- LGD (Local Government Directory, Ministry of Panchayati Raj) village directory
  and village-to-PIN mapping, as republished daily from lgdirectory.gov.in at
  github.com/ramSeraph/opendata (release "lgd-latest").
- OpenStreetMap named suburbs, neighbourhoods and quarters in India, via the
  Overpass API. OSM data is (c) OpenStreetMap contributors, ODbL 1.0.

After downloading, the reference index is rebuilt automatically on the next
app start, or immediately with: python scripts/build_reference_index.py
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import httpx
import py7zr

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LGD_LISTING = "https://github.com/ramSeraph/opendata/releases/download/lgd-latest/listing_files.csv"
OVERPASS_URLS = [
    u for u in (os.getenv("OVERPASS_URL"),) if u
] + [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_QUERY = """
[out:json][timeout:900];
area["ISO3166-1"="IN"][admin_level=2]->.in;
(
  node["place"~"^(suburb|neighbourhood|quarter)$"]["name"](area.in);
  way["place"~"^(suburb|neighbourhood|quarter)$"]["name"](area.in);
  relation["place"~"^(suburb|neighbourhood|quarter)$"]["name"](area.in);
);
out center tags;
"""
HEADERS = {"User-Agent": "AddressGuard-AI/1.0 (reference data build)"}


# ---------------------------------------------------------------- LGD

def _latest_lgd_urls(names):
    listing = httpx.get(LGD_LISTING, headers=HEADERS, timeout=60, follow_redirects=True)
    listing.raise_for_status()
    latest = {}
    for row in csv.DictReader(io.StringIO(listing.text)):
        match = re.match(r"^([a-z_]+)\.(\d{2}[A-Za-z]{3}\d{4})\.csv\.7z$", row.get("name", ""))
        if not match or match.group(1) not in names:
            continue
        from datetime import datetime
        stamp = datetime.strptime(match.group(2), "%d%b%Y")
        if match.group(1) not in latest or stamp > latest[match.group(1)][0]:
            latest[match.group(1)] = (stamp, row["url"])
    missing = set(names) - set(latest)
    if missing:
        raise RuntimeError(f"LGD listing has no files for: {sorted(missing)}")
    return {name: url for name, (_, url) in latest.items()}, max(s for s, _ in latest.values())


def _download_and_extract(url, target):
    """Download a single-CSV .7z archive and write its CSV to target."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "download.7z"
        with httpx.stream("GET", url, headers=HEADERS, timeout=httpx.Timeout(600, connect=30), follow_redirects=True) as r:
            r.raise_for_status()
            with archive.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        with py7zr.SevenZipFile(archive, "r") as z:
            members = [n for n in z.getnames() if n.lower().endswith(".csv") and "/" not in n and "\\" not in n]
            if len(members) != 1:
                raise RuntimeError(f"unexpected archive contents: {z.getnames()}")
            z.extract(path=tmp, targets=members)
        os.replace(Path(tmp) / members[0], target)


def fetch_lgd():
    urls, stamp = _latest_lgd_urls({"villages", "pincode_villages"})
    print(f"LGD snapshot {stamp:%d %b %Y}")
    for name, target in (("villages", DATA / "lgd_villages.csv"),
                         ("pincode_villages", DATA / "lgd_pincode_villages.csv")):
        _download_and_extract(urls[name], target)
        with target.open(encoding="utf-8-sig", newline="") as fh:
            rows = sum(1 for _ in fh) - 1
        print(f"  {target.name}: {rows:,} rows")


# ---------------------------------------------------------------- OpenStreetMap

def _overpass():
    last = None
    for url in OVERPASS_URLS:
        try:
            print(f"  querying {url} (this can take a few minutes)")
            r = httpx.post(url, data={"data": OVERPASS_QUERY}, headers=HEADERS,
                           timeout=httpx.Timeout(900, connect=30))
            r.raise_for_status()
            payload = r.json()
            if payload.get("remark") and "error" in payload["remark"].lower():
                raise RuntimeError(payload["remark"])
            return payload
        except Exception as exc:  # try the next public mirror
            last = exc
            print(f"    unavailable: {type(exc).__name__}")
    raise RuntimeError(f"no Overpass endpoint reachable ({type(last).__name__})")


def _post_office_grid():
    """Bucket India Post offices with coordinates into 0.1-degree cells."""
    grid = {}
    with (DATA / "india_post_pincode.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                lat, lon = float(row.get("latitude") or ""), float(row.get("longitude") or "")
            except ValueError:
                continue
            if not (6 <= lat <= 38 and 68 <= lon <= 98):  # outside India: bad coordinates
                continue
            key = (round(lat, 1), round(lon, 1))
            grid.setdefault(key, []).append((lat, lon, row.get("district", ""), row.get("statename", "")))
    return grid


def _nearest(grid, lat, lon, max_km=15):
    best = None
    base = (round(lat, 1), round(lon, 1))
    for dlat in (-0.1, 0, 0.1):
        for dlon in (-0.1, 0, 0.1):
            for plat, plon, district, state in grid.get((round(base[0] + dlat, 1), round(base[1] + dlon, 1)), []):
                km = math.hypot((plat - lat) * 111, (plon - lon) * 111 * math.cos(math.radians(lat)))
                if best is None or km < best[0]:
                    best = (km, district, state)
    return best if best and best[0] <= max_km else None


def fetch_osm():
    payload = _overpass()
    elements = payload.get("elements", [])
    print(f"  {len(elements):,} OSM elements")
    grid = _post_office_grid()
    target = DATA / "osm_localities.csv"
    written = 0
    with target.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["osm_id", "name", "place", "latitude", "longitude", "postcode",
                    "district", "state", "context_source"])
        seen = set()
        for el in elements:
            tags = el.get("tags") or {}
            name = (tags.get("name:en") or tags.get("name") or "").strip()
            # Keep Latin-script names only; the address text being validated is in English.
            if not name or not re.search(r"[A-Za-z]", name) or re.search(r"[^\x00-\x7F]", name):
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            postcode = re.sub(r"\D", "", tags.get("addr:postcode") or tags.get("postal_code") or "")
            postcode = postcode if len(postcode) == 6 else ""
            near = _nearest(grid, float(lat), float(lon))
            district, state = (near[1], near[2]) if near else ("", "")
            key = (name.lower(), district.lower(), state.lower())
            if key in seen:
                continue
            seen.add(key)
            w.writerow([f"{el['type']}/{el['id']}", name, tags.get("place", ""), lat, lon, postcode,
                        district, state, "nearest India Post office" if near else ""])
            written += 1
    print(f"  {target.name}: {written:,} localities (OSM base {payload.get('osm3s', {}).get('timestamp_osm_base', '?')})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lgd", action="store_true", help="download LGD villages and village PIN codes")
    parser.add_argument("--osm", action="store_true", help="download OpenStreetMap localities")
    args = parser.parse_args()
    both = not (args.lgd or args.osm)
    failed = False
    if args.lgd or both:
        print("Downloading LGD village data...")
        try:
            fetch_lgd()
        except Exception as exc:
            failed = True
            print(f"  LGD download failed: {type(exc).__name__}: {exc}")
    if args.osm or both:
        print("Downloading OpenStreetMap localities...")
        try:
            fetch_osm()
        except Exception as exc:
            failed = True
            print(f"  OSM download failed: {type(exc).__name__}: {exc}")
    print("Rebuild the index with: python scripts/build_reference_index.py")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
