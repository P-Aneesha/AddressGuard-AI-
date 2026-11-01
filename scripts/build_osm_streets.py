#!/usr/bin/env python3
"""Extract every named road in India from the Geofabrik OpenStreetMap extracts.

    python scripts/build_osm_streets.py            # writes data/osm_streets.csv

Downloads the six India regions from download.geofabrik.de (about 1.7 GB in
total), one at a time, and deletes each after use. Needs `pip install osmium`
(see requirements-data.txt). Each road is placed at the midpoint of its nodes
and assigned to the state of the nearest India Post office; segments of the
same road in the same ~1 km cell are merged. Only Latin-script names are kept.

OpenStreetMap does not map every Indian street; this is its complete
named-road coverage. Data (c) OpenStreetMap contributors, ODbL 1.0.
"""
import csv
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import httpx
import osmium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_reference_data import HEADERS, _post_office_grid  # noqa: E402
from services.official_reference_service import _canon_state  # noqa: E402

DATA = ROOT / "data"
ZONES = ["north-eastern", "eastern", "western", "northern", "central", "southern"]
URL = "https://download.geofabrik.de/asia/india/{zone}-zone-latest.osm.pbf"
ROAD_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
              "living_street", "service", "road"}


def _state_of(grid, lat, lon, k=7, max_km=20):
    """State by majority of the nearest post offices.

    A few India Post offices carry wrong coordinates (a Tamil Nadu office placed
    in Hyderabad), so a single nearest office can give the wrong state.
    """
    import math
    found = []
    base = (round(lat, 1), round(lon, 1))
    for dlat in (-0.2, -0.1, 0, 0.1, 0.2):
        for dlon in (-0.2, -0.1, 0, 0.1, 0.2):
            for plat, plon, _district, state in grid.get((round(base[0] + dlat, 1), round(base[1] + dlon, 1)), []):
                km = math.hypot((plat - lat) * 111, (plon - lon) * 111 * math.cos(math.radians(lat)))
                if km <= max_km and state:
                    found.append((km, state))
    if not found:
        return ""
    votes = {}
    for _km, state in sorted(found)[:k]:
        votes[state] = votes.get(state, 0) + 1
    return max(votes, key=votes.get)


def relabel(path):
    """Recompute the state column of an existing road CSV (no download)."""
    grid = _post_office_grid()
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    kept = 0
    with path.with_suffix(".partial").open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(["name", "latitude", "longitude", "state"])
        for r in rows:
            state = _state_of(grid, float(r["latitude"]), float(r["longitude"]))
            if state:
                w.writerow([r["name"], r["latitude"], r["longitude"], _canon_state(state)])
                kept += 1
    os.replace(path.with_suffix(".partial"), path)
    print(f"{path.name}: {kept:,} of {len(rows):,} roads labelled with a state")


def _download(zone, folder):
    path = Path(folder) / f"{zone}.osm.pbf"
    with httpx.stream("GET", URL.format(zone=zone), headers=HEADERS, timeout=httpx.Timeout(120, read=600),
                      follow_redirects=True) as r:
        r.raise_for_status()
        with path.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
    return path


def _roads(path):
    """Yield (name, lat, lon) for every named road way in the file."""
    processor = (osmium.FileProcessor(str(path)).with_locations()
                 .with_filter(osmium.filter.KeyFilter("highway")))
    for obj in processor:
        if not obj.is_way() or obj.tags.get("highway") not in ROAD_TYPES:
            continue
        name = (obj.tags.get("name:en") or obj.tags.get("name") or "").strip()
        if not name or not re.search(r"[A-Za-z]", name) or re.search(r"[^\x00-\x7F]", name):
            continue
        points = [(n.lat, n.lon) for n in obj.nodes if n.location.valid()]
        if points:
            mid = points[len(points) // 2]
            yield name, mid[0], mid[1]


def main():
    target = Path(os.getenv("OSM_STREETS_OUTPUT") or DATA / "osm_streets.csv")
    partial = target.with_suffix(".partial")
    grid = _post_office_grid()
    seen, written = set(), 0
    with partial.open("w", encoding="utf-8", newline="") as out, tempfile.TemporaryDirectory() as tmp:
        w = csv.writer(out)
        w.writerow(["name", "latitude", "longitude", "state"])
        for zone in ZONES:
            started = time.time()
            path = _download(zone, tmp)
            before = written
            for name, lat, lon in _roads(path):
                key = (name.lower(), round(lat, 2), round(lon, 2))
                if key in seen:
                    continue
                state = _state_of(grid, lat, lon)
                if not state:
                    continue  # outside India Post coverage (sea, border areas)
                seen.add(key)
                w.writerow([name, f"{lat:.6f}", f"{lon:.6f}", _canon_state(state)])
                written += 1
            path.unlink()
            print(f"  {zone}: {written - before:,} named roads ({time.time() - started:.0f} s)", flush=True)
    os.replace(partial, target)
    print(f"{target.name}: {written:,} named roads across India")


if __name__ == "__main__":
    if "--relabel" in sys.argv:
        relabel(Path(os.getenv("OSM_STREETS_OUTPUT") or DATA / "osm_streets.csv"))
    else:
        main()
