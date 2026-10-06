#!/usr/bin/env python3
"""Build a fast SQLite index for AddressGuard's three supplied whole-India CSVs.

The original CSVs remain in data/ for traceability. The SQLite index is a runtime
cache only; rebuild it whenever the CSV snapshots change.
"""
from __future__ import annotations
import csv, re, sqlite3, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "reference_index.sqlite3"
PIN = DATA / "india_post_pincode.csv"
VILL = DATA / "lgd_villages.csv"
MAP = DATA / "postal_lgd_mapping.csv"


def norm(v: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(v or "").strip().lower()).split())

def digits(v: str) -> str:
    return re.sub(r"\D", "", str(v or ""))[:6]

def idxmap(headers):
    return {norm(h).replace(" ", "_"): i for i, h in enumerate(headers)}

def col(m, row, *names):
    for n in names:
        i = m.get(n)
        if i is not None and i < len(row):
            v = row[i].strip()
            if v:
                return v
    return ""

def read_header(path: Path):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        fh = None
        try:
            fh = path.open("r", encoding=enc, newline="")
            r = csv.reader(fh); headers = next(r)
            return fh, r, idxmap(headers)
        except UnicodeDecodeError:
            if fh: fh.close(); continue
    raise RuntimeError(f"Cannot read {path}")

def insert_batch(con, sql, batch):
    if batch:
        con.executemany(sql, batch)
        batch.clear()

def build():
    for p in (PIN, VILL, MAP):
        if not p.exists():
            raise FileNotFoundError(f"Missing {p}")
    if DB.exists(): DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-100000")
    con.execute("PRAGMA locking_mode=EXCLUSIVE")
    con.executescript('''
      CREATE TABLE postal_offices(
        id INTEGER PRIMARY KEY, officename TEXT, norm_name TEXT, pincode TEXT,
        officetype TEXT, delivery TEXT, divisionname TEXT, regionname TEXT,
        circlename TEXT, taluk TEXT, norm_taluk TEXT, district TEXT, norm_district TEXT,
        statename TEXT, norm_state TEXT, latitude TEXT, longitude TEXT
      );
      CREATE TABLE villages(
        id INTEGER PRIMARY KEY, state_code TEXT, state_name TEXT, norm_state TEXT,
        district_code TEXT, district_name TEXT, norm_district TEXT,
        subdistrict_code TEXT, subdistrict_name TEXT, norm_subdistrict TEXT,
        village_code TEXT, village_name TEXT, norm_village TEXT,
        localbody_code TEXT, localbody_name TEXT, block_code TEXT, block_name TEXT, norm_block TEXT
      );
      CREATE TABLE pin_lgd(
        id INTEGER PRIMARY KEY, pincode TEXT, state TEXT, norm_state TEXT,
        district TEXT, norm_district TEXT, blocks TEXT, state_lgd TEXT, district_lgd TEXT
      );
    ''')

    fh, r, m = read_header(PIN); batch=[]; count=0
    try:
        for row in r:
            office=col(m,row,'officename','office_name','post_office','postoffice')
            pin=digits(col(m,row,'pincode','pin_code','pin'))
            if not office and not pin: continue
            district=col(m,row,'district','districtname','district_name'); state=col(m,row,'statename','state_name','state')
            taluk=col(m,row,'taluk','subdistrict','sub_district','tehsil')
            # Normalize postal-office display suffixes for lookup.  Parenthetical
            # qualifiers such as "Indiranagar S.O (Bengaluru)" are removed from
            # the searchable name; PIN/state/district context still disambiguates
            # duplicate names.
            clean_off=re.sub(r"\s*\([^)]*\)", "", office)
            clean_off=re.sub(r"\s+(?:s\.o\.?|b\.o\.?|h\.o\.?|d\.o\.?)$", "", clean_off, flags=re.I)
            clean_off=re.sub(r"\s+", " ", clean_off).strip()
            batch.append((office,norm(clean_off),pin,col(m,row,'officetype','office_type'),col(m,row,'delivery','deliverystatus','delivery_status'),col(m,row,'divisionname','division_name','division'),col(m,row,'regionname','region_name','region'),col(m,row,'circlename','circle_name','circle'),taluk,norm(taluk),district,norm(district),state,norm(state),col(m,row,'latitude','lat'),col(m,row,'longitude','lon','lng')))
            if len(batch)>=20000: insert_batch(con,"INSERT INTO postal_offices(officename,norm_name,pincode,officetype,delivery,divisionname,regionname,circlename,taluk,norm_taluk,district,norm_district,statename,norm_state,latitude,longitude) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch); count += 20000
    finally: fh.close()
    insert_batch(con,"INSERT INTO postal_offices(officename,norm_name,pincode,officetype,delivery,divisionname,regionname,circlename,taluk,norm_taluk,district,norm_district,statename,norm_state,latitude,longitude) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
    # exact count from DB is cheap
    print("India Post:", con.execute("select count(*) from postal_offices").fetchone()[0])

    fh, r, m = read_header(VILL); batch=[]
    try:
        for row in r:
            village=col(m,row,'village_name_in_english','village_name','village','name')
            if not village: continue
            state=col(m,row,'state_name_in_english','state_name','state'); district=col(m,row,'district_name_in_english','district_name','district'); sub=col(m,row,'subdistrict_name_in_english','subdistrict_name','subdistrict','sub_district','taluk','tehsil'); block=col(m,row,'block_name_in_english','block_name','block')
            batch.append((col(m,row,'state_code'),state,norm(state),col(m,row,'district_code'),district,norm(district),col(m,row,'subdistrict_code','sub_district_code'),sub,norm(sub),col(m,row,'village_code'),village,norm(village),col(m,row,'localbody_code','local_body_code'),col(m,row,'localbody_name_in_english','localbody_name'),col(m,row,'block_code'),block,norm(block)))
            if len(batch)>=20000: insert_batch(con,"INSERT INTO villages(state_code,state_name,norm_state,district_code,district_name,norm_district,subdistrict_code,subdistrict_name,norm_subdistrict,village_code,village_name,norm_village,localbody_code,localbody_name,block_code,block_name,norm_block) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
    finally: fh.close()
    insert_batch(con,"INSERT INTO villages(state_code,state_name,norm_state,district_code,district_name,norm_district,subdistrict_code,subdistrict_name,norm_subdistrict,village_code,village_name,norm_village,localbody_code,localbody_name,block_code,block_name,norm_block) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
    print("LGD villages:", con.execute("select count(*) from villages").fetchone()[0])

    fh, r, m = read_header(MAP); batch=[]
    try:
        for row in r:
            pin=digits(col(m,row,'pincode','pin','pin_code'))
            if not pin: continue
            state=col(m,row,'state','statename','state_name'); district=col(m,row,'district','districtname','district_name')
            batch.append((pin,state,norm(state),district,norm(district),col(m,row,'blocks'),col(m,row,'state_lgd','state_code'),col(m,row,'district_lgd','district_code')))
            if len(batch)>=20000: insert_batch(con,"INSERT INTO pin_lgd(pincode,state,norm_state,district,norm_district,blocks,state_lgd,district_lgd) VALUES (?,?,?,?,?,?,?,?)",batch)
    finally: fh.close()
    insert_batch(con,"INSERT INTO pin_lgd(pincode,state,norm_state,district,norm_district,blocks,state_lgd,district_lgd) VALUES (?,?,?,?,?,?,?,?)",batch)
    print("Postal-LGD mapping:", con.execute("select count(*) from pin_lgd").fetchone()[0])

    con.commit()
    print("Creating indexes...")
    con.executescript('''
      CREATE INDEX idx_post_pin ON postal_offices(pincode);
      CREATE INDEX idx_post_name ON postal_offices(norm_name);
      CREATE INDEX idx_post_name_state_district ON postal_offices(norm_name,norm_state,norm_district);
      CREATE INDEX idx_post_state_district ON postal_offices(norm_state,norm_district);
      CREATE INDEX idx_post_pin_state ON postal_offices(pincode,norm_state);
      CREATE INDEX idx_post_pin_district ON postal_offices(pincode,norm_district);
      CREATE INDEX idx_vill_name ON villages(norm_village);
      CREATE INDEX idx_vill_name_state_district ON villages(norm_village,norm_state,norm_district);
      CREATE INDEX idx_vill_state_district ON villages(norm_state,norm_district);
      CREATE INDEX idx_vill_district ON villages(norm_district);
      CREATE INDEX idx_vill_sub ON villages(norm_subdistrict);
      CREATE INDEX idx_pinlgd_pin ON pin_lgd(pincode);
      CREATE INDEX idx_pinlgd_state_dist ON pin_lgd(norm_state,norm_district);
    ''')
    con.commit(); con.execute("ANALYZE"); con.close()
    print(f"Built {DB} ({DB.stat().st_size/1e6:.1f} MB)")

if __name__ == '__main__': build()
