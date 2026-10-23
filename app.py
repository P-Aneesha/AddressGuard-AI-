import logging
import os
import re
import psycopg2
from flask import Flask, jsonify, request
from flask_migrate import Migrate
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException
from config import Config
from models import db
from models.user import User
from models.validation import Validation
from models.rate_limit import RateLimitHit  # noqa: F401  (table created by create_all)
from routes.auth import auth_bp
from routes.views import views_bp
from routes.api import api_bp
from services.decision_labels import LEGACY_DECISIONS
from services.official_reference_service import get_reference_status
from utils.dns_fallback import resolve_via_public_dns, system_can_resolve

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("addressguard.app")


def migrate_legacy_decisions():
    """Rename decision labels stored by older releases.

    Idempotent and non-destructive: only the decision column of rows that still
    hold a legacy label is updated; no rows are deleted.
    """
    updated = 0
    for old, new in LEGACY_DECISIONS.items():
        updated += Validation.query.filter_by(decision=old).update(
            {Validation.decision: new}, synchronize_session=False
        )
    db.session.commit()
    return updated


def _register_error_handlers(app):
    # API clients always receive JSON errors without stack traces or internals.
    def _wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        if not _wants_json():
            return exc
        messages = {
            400: "The request could not be understood. Please check the submitted data.",
            404: "The requested resource was not found.",
            405: "This action is not allowed for the requested resource.",
            413: "The submitted data is too large.",
        }
        return jsonify({"error": messages.get(exc.code, exc.description or "Request failed")}), exc.code

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(exc):
        db.session.rollback()
        logger.exception("Database error on %s", request.path)
        return jsonify({
            "error": "The database is temporarily unavailable. Please try again shortly.",
            "error_type": "TECHNICAL_FAILURE",
        }), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        logger.exception("Unhandled error on %s", request.path)
        if _wants_json():
            return jsonify({
                "error": "An unexpected technical problem occurred. Please try again.",
                "error_type": "TECHNICAL_FAILURE",
            }), 500
        return "An unexpected error occurred. Please try again.", 500


def _configure_database(app):
    """Require PostgreSQL and set connection-pool options suited to it.

    The automated test suite runs on a throwaway SQLite file and opts in with
    ADDRESSGUARD_TEST_ALLOW_SQLITE=1; the application itself never does.
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if uri.startswith("postgresql"):
        app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {
            "pool_pre_ping": True,      # managed PostgreSQL (e.g. Neon) closes idle connections
            "pool_recycle": 280,
            "connect_args": {"connect_timeout": 10},
        })
        return
    if uri and os.getenv("ADDRESSGUARD_TEST_ALLOW_SQLITE") == "1":
        return
    raise RuntimeError(
        "AddressGuard requires PostgreSQL. Set DATABASE_URL in .env to a PostgreSQL connection "
        "string, e.g. postgresql://user:password@host/dbname?sslmode=require"
        + ("" if not uri else f" (got a '{uri.split(':', 1)[0]}' URL)")
    )


def _database_host(uri):
    match = re.search(r"@([^/:?]+)", uri or "")
    return match.group(1) if match else "the database server"


def _host_lookup_fails(uri):
    """Probe one real connection; True only when it fails on host-name lookup."""
    try:
        psycopg2.connect(uri, connect_timeout=10).close()
    except psycopg2.OperationalError as exc:
        return "translate host name" in str(exc)
    except Exception:
        return False
    return False


def _apply_dns_fallback(app):
    """Connect by IP when the local DNS cannot resolve the PostgreSQL host.

    The local resolver is checked and, if it answers, a real connection is
    probed too, because a flaky router can answer one lookup and fail the next.
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    host = _database_host(uri)
    if not uri.startswith("postgresql") or host == "the database server" or os.getenv("VERCEL"):
        return False  # hosted platforms resolve DNS normally; skip the probe connection
    if system_can_resolve(host) and not _host_lookup_fails(uri):
        return False
    address = None
    for _ in range(3):  # a single UDP reply can be lost on a flaky network
        address = resolve_via_public_dns(host)
        if address:
            break
    if not address:
        app.logger.warning("Public DNS lookup for %s failed as well", host)
        return False
    connect_args = app.config["SQLALCHEMY_ENGINE_OPTIONS"].setdefault("connect_args", {})
    connect_args["hostaddr"] = address
    app.logger.info("Local DNS could not resolve %s; connecting via public DNS result %s", host, address)
    return True


def _configure_hosting(app):
    """Production hardening when running on Vercel (HTTPS, public internet)."""
    if not os.getenv("VERCEL"):
        return
    secret = app.config.get("SECRET_KEY") or ""
    if len(secret) < 32 or secret.lower().startswith(("change", "your")):
        raise RuntimeError("SECRET_KEY must be set to a random value of at least 32 characters on Vercel")
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    # Reject oversized request bodies before they reach the validation code.
    app.config.setdefault("MAX_CONTENT_LENGTH", 64 * 1024)
    if test_config:
        app.config.update(test_config)
    _configure_hosting(app)
    _configure_database(app)
    _apply_dns_fallback(app)
    app.logger.info("Groq configured: %s (model=%s)",
                     bool(app.config.get("GROQ_API_KEY")), app.config.get("GROQ_MODEL"))
    db.init_app(app)
    Migrate(app, db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    _register_error_handlers(app)
    with app.app_context():
        try:
            db.create_all()
        except OperationalError as exc:
            host = _database_host(app.config["SQLALCHEMY_DATABASE_URI"])
            reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0].rstrip(". ")
            raise RuntimeError(
                f"Cannot connect to PostgreSQL at {host}: {reason}. "
                "Check DATABASE_URL, your internet connection and DNS settings."
            ) from None
        try:
            renamed = migrate_legacy_decisions()
            if renamed:
                app.logger.info("Migrated %s validation record(s) to the current decision labels", renamed)
        except SQLAlchemyError as exc:
            db.session.rollback()
            app.logger.warning("Legacy decision migration skipped: %s", type(exc).__name__)
    # Build/validate the local whole-India reference index once at startup.
    # If the reference files are missing, keep the app usable and let the
    # validation layer report the missing-data condition instead of crashing.
    try:
        ref_status = get_reference_status()
        app.logger.info(
            "Reference data: India Post=%s (%s rows), LGD villages=%s (%s rows), mapping=%s (%s rows)",
            ref_status.get("india_post_file"), ref_status.get("india_post_rows", 0),
            ref_status.get("lgd_villages_file"), ref_status.get("lgd_village_rows", 0),
            ref_status.get("postal_lgd_mapping_file"), ref_status.get("postal_lgd_mapping_rows", 0),
        )
    except Exception as exc:
        app.logger.warning("Reference-data index unavailable at startup: %s", type(exc).__name__)
    return app

try:
    app = create_app()
except RuntimeError as exc:
    if __name__ == "__main__":
        print(f"\nAddressGuard could not start: {exc}\n")
        raise SystemExit(1)
    raise

if __name__ == "__main__":
    app.run(debug=True)
