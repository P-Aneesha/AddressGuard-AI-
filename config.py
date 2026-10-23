import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _clean(v: str) -> str:
    v = (v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v.strip()


def _database_url(v: str) -> str:
    """PostgreSQL is the only supported database. Some hosts hand out the
    legacy "postgres://" scheme, which SQLAlchemy expects as "postgresql://"."""
    v = _clean(v)
    if v.startswith("postgres://"):
        v = "postgresql://" + v[len("postgres://"):]
    return v


class Config:
    SECRET_KEY = _clean(os.getenv("SECRET_KEY", "change-this"))
    # Required: a PostgreSQL connection string. There is deliberately no
    # SQLite fallback; create_app() refuses to start without PostgreSQL.
    SQLALCHEMY_DATABASE_URI = _database_url(os.getenv("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # The .env.example placeholder is not a key; treat it as unset so the
    # pipeline uses the deterministic fallback instead of failing with HTTP 401.
    GROQ_API_KEY = _clean(os.getenv("GROQ_API_KEY", ""))
    if GROQ_API_KEY.lower().startswith("your_"):
        GROQ_API_KEY = ""
    GROQ_BASE_URL = _clean(os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    GROQ_MODEL = _clean(os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    GROQ_TIMEOUT_SECONDS = int(_clean(os.getenv("GROQ_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "15"))

    PUBLIC_BASE_URL = _clean(os.getenv("PUBLIC_BASE_URL", "http://localhost:5000"))

    GEOCODING_ENABLED = _clean(os.getenv("GEOCODING_ENABLED", "false")).lower() in {"1", "true", "yes", "on"}
    GEOCODING_URL = _clean(os.getenv("GEOCODING_URL", "https://nominatim.openstreetmap.org/search"))
    GEOCODING_TIMEOUT_SECONDS = int(_clean(os.getenv("GEOCODING_TIMEOUT_SECONDS", "8")))

    # Whole-India reference data bundled with this project.
    OFFICIAL_REFERENCE_ENABLED = _clean(os.getenv("OFFICIAL_REFERENCE_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
    INDIA_POST_PINCODE_CSV = _clean(os.getenv("INDIA_POST_PINCODE_CSV", str(BASE_DIR / "data" / "india_post_pincode.csv")))
    LGD_VILLAGES_CSV = _clean(os.getenv("LGD_VILLAGES_CSV", str(BASE_DIR / "data" / "lgd_villages.csv")))
    POSTAL_LGD_MAPPING_CSV = _clean(os.getenv("POSTAL_LGD_MAPPING_CSV", str(BASE_DIR / "data" / "postal_lgd_mapping.csv")))
    REFERENCE_INDEX_DB = _clean(os.getenv("REFERENCE_INDEX_DB", str(BASE_DIR / "data" / "reference_index.sqlite3")))
    REFERENCE_INDEX_BUILD_TIMEOUT = int(_clean(os.getenv("REFERENCE_INDEX_BUILD_TIMEOUT", "180")))

    # Backward-compatible names for older deployments.
    LGD_VILLAGES_PIN_CSV = _clean(os.getenv("LGD_VILLAGES_PIN_CSV", str(BASE_DIR / "data" / "lgd_villages_with_pin.csv")))
    LGD_ADMIN_CSV = _clean(os.getenv("LGD_ADMIN_CSV", str(BASE_DIR / "data" / "lgd_admin.csv")))

    # Optional official data.gov.in API sync.
    DATA_GOV_API_KEY = _clean(os.getenv("DATA_GOV_API_KEY", ""))
    DATA_GOV_PINCODE_RESOURCE_ID = _clean(os.getenv("DATA_GOV_PINCODE_RESOURCE_ID", ""))
    OFFICIAL_REFERENCE_TIMEOUT = int(_clean(os.getenv("OFFICIAL_REFERENCE_TIMEOUT", "20")))

    # Local nationwide data is the primary lookup. This live API is only a fallback
    # for a PIN/place not found in the bundled snapshot.
    LIVE_POSTAL_API_ENABLED = _clean(os.getenv("LIVE_POSTAL_API_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
    LIVE_POSTAL_API_BASE_URL = _clean(os.getenv("LIVE_POSTAL_API_BASE_URL", "https://api.pincodeapi.in/api/v1"))
    LIVE_POSTAL_API_TIMEOUT = int(_clean(os.getenv("LIVE_POSTAL_API_TIMEOUT", "8")))
    LIVE_POSTAL_CACHE_TTL_SECONDS = int(_clean(os.getenv("LIVE_POSTAL_CACHE_TTL_SECONDS", "600")))
