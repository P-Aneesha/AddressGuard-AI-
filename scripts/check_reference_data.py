#!/usr/bin/env python3
"""Validate the three supplied whole-India reference CSVs and index."""
from pathlib import Path
import csv
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    ("India Post PIN directory", ROOT / "data" / "india_post_pincode.csv"),
    ("LGD village directory", ROOT / "data" / "lgd_villages.csv"),
    ("Postal-LGD mapping", ROOT / "data" / "postal_lgd_mapping.csv"),
]

for name, path in FILES:
    if not path.exists():
        print(f"[MISSING] {name}: {path}")
        continue
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            count = sum(1 for _ in reader)
        print(f"[READY]   {name}: {count:,} rows; columns={len(header)}")
    except Exception as exc:
        print(f"[ERROR]   {name}: {exc}")

index_path = ROOT / "data" / "reference_index.sqlite3"
if index_path.exists():
    try:
        with sqlite3.connect(index_path) as con:
            print(f"[INDEX]   India Post rows: {con.execute('SELECT count(*) FROM postal_offices').fetchone()[0]:,}")
            print(f"[INDEX]   LGD village rows: {con.execute('SELECT count(*) FROM villages').fetchone()[0]:,}")
            print(f"[INDEX]   Postal-LGD rows: {con.execute('SELECT count(*) FROM pin_lgd').fetchone()[0]:,}")
    except Exception as exc:
        print(f"[INDEX ERROR] {exc}")
else:
    print("[INDEX]   Not built yet. Run: python scripts/build_reference_index.py")
