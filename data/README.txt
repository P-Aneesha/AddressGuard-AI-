AddressGuard AI — Project Reference Dataset
=============================================

This package was prepared from the project's existing official/reference CSV files.
It is a CLEANED/INDEXED version, not a fabricated replacement dataset.

Source files:
- India Post PIN directory
- LGD village directory
- Postal-LGD mapping

Cleaning performed:
- whitespace normalization
- empty-string normalization
- exact duplicate removal
- conservative normalized search columns
- preservation of source and record type
- SQLite indexes for PIN/name/state/district searches

IMPORTANT:
- No place was invented.
- No missing locality was artificially filled.
- Different source names were NOT blindly merged.
- "Not found in reference" must not be treated as "invalid address".
- LGD is not a complete street/building/flat/landmark database.
- India Post is a postal reference directory, not a complete list of every physical address.

Audit summary:
{
  "india_post_pincode.csv": {
    "original_rows": 165627,
    "duplicate_rows_removed": 2,
    "final_rows": 165625
  },
  "lgd_villages.csv": {
    "original_rows": 689682,
    "duplicate_rows_removed": 0,
    "final_rows": 689682
  },
  "postal_lgd_mapping.csv": {
    "original_rows": 20144,
    "duplicate_rows_removed": 0,
    "final_rows": 20144
  }
}


Additional datasets (downloaded by scripts/fetch_reference_data.py)
-------------------------------------------------------------------
- lgd_villages.csv: LGD village directory (Ministry of Panchayati Raj,
  lgdirectory.gov.in), daily mirror github.com/ramSeraph/opendata.
- lgd_pincode_villages.csv: LGD village-to-PIN mapping from the same source.
- osm_localities.csv: named suburbs/neighbourhoods/quarters in India from
  OpenStreetMap (Overpass API). District/state are copied from the nearest
  India Post office (within 15 km) and are therefore approximate.
  OpenStreetMap data (c) OpenStreetMap contributors, ODbL 1.0.
