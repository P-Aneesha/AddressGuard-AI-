"""Test-session setup.

Importing ``app`` builds the Flask app against the configured database, so the
database URL is pointed at a throwaway SQLite file before any test module
imports ``config``. This keeps test runs away from the real development or
production database. python-dotenv does not override variables that are
already set, so .env cannot redirect tests back to the real database.
"""
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="addressguard-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TEST_DB_DIR, "session.db").replace("\\", "/")
# The app itself is PostgreSQL-only; tests explicitly opt in to a throwaway SQLite file.
os.environ["ADDRESSGUARD_TEST_ALLOW_SQLITE"] = "1"
os.environ.setdefault("SECRET_KEY", "test")
os.environ["GROQ_API_KEY"] = ""
