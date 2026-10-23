"""Copy the runtime settings from .env to the linked Vercel project.

    vercel login
    vercel link
    python scripts/vercel_env_sync.py            # production environment
    python scripts/vercel_env_sync.py preview    # or another environment

Values are piped to `vercel env add` and never printed. SECRET_KEY is not
copied: production gets its own freshly generated key. Local file paths
(CSV/index locations) are not copied; Vercel uses the packaged index.
"""
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SYNCED = (
    "DATABASE_URL", "GROQ_API_KEY", "GROQ_BASE_URL", "GROQ_MODEL", "OPENAI_TIMEOUT_SECONDS",
    "GEOCODING_ENABLED", "GEOCODING_URL", "GEOCODING_TIMEOUT_SECONDS", "OFFICIAL_REFERENCE_ENABLED",
    "LIVE_POSTAL_API_ENABLED", "LIVE_POSTAL_API_BASE_URL", "LIVE_POSTAL_API_TIMEOUT",
    "LIVE_POSTAL_CACHE_TTL_SECONDS", "DATA_GOV_API_KEY", "DATA_GOV_PINCODE_RESOURCE_ID",
)


def _vercel():
    exe = shutil.which("vercel") or shutil.which("vercel.cmd")
    if not exe:
        sys.exit("Vercel CLI not found. Install it with: npm i -g vercel")
    return exe


def _set(exe, name, value, environment):
    # Replace any existing value so re-running the script is safe.
    subprocess.run([exe, "env", "rm", name, environment, "--yes"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run([exe, "env", "add", name, environment], cwd=ROOT, input=value, text=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        sys.exit(f"Could not set {name}: {result.stderr.strip()[-300:]}")
    print(f"set {name}")


def main():
    environment = sys.argv[1] if len(sys.argv) > 1 else "production"
    values = dotenv_values(ROOT / ".env")
    if not str(values.get("DATABASE_URL") or "").strip().strip("'\"").startswith(("postgres://", "postgresql://")):
        sys.exit("DATABASE_URL in .env must be a PostgreSQL connection string")
    exe = _vercel()
    for name in SYNCED:
        value = str(values.get(name) or "").strip().strip("'\"")
        if value:
            _set(exe, name, value, environment)
    _set(exe, "SECRET_KEY", secrets.token_hex(32), environment)


if __name__ == "__main__":
    main()
