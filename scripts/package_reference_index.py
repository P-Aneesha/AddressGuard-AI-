"""Compress the reference index for serverless deployment (Vercel).

    python scripts/package_reference_index.py

Writes data/reference_index.sqlite3.gz (about 50 MB from the 226 MB index).
Deploy that file instead of the raw CSVs and the uncompressed index; the app
unpacks it into the temp folder on a cold start (see _packaged_index in
services/official_reference_service.py). Re-run after rebuilding the index.
"""
import gzip
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "reference_index.sqlite3"
TARGET = ROOT / "data" / "reference_index.sqlite3.gz"


def main():
    if not SOURCE.exists():
        sys.exit(f"Missing {SOURCE}; build it first with scripts/build_reference_index.py")
    with sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True) as con:
        offices = con.execute("SELECT count(*) FROM postal_offices").fetchone()[0]
    partial = TARGET.with_suffix(".gz.partial")
    with open(SOURCE, "rb") as src, gzip.open(partial, "wb", compresslevel=9) as out:
        shutil.copyfileobj(src, out, 1 << 20)
    partial.replace(TARGET)
    print(f"{TARGET} ({TARGET.stat().st_size / 1048576:.1f} MB, {offices:,} post offices)")


if __name__ == "__main__":
    main()
