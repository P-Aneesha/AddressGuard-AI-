"""The application database must be PostgreSQL."""
import os
from unittest import mock

import pytest
from flask import Flask

from app import _configure_database, create_app
from config import _database_url


def _app(uri):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    return app


@pytest.mark.parametrize("uri", ["", "sqlite:///addressguard.db", "mysql://u:p@h/db"])
def test_non_postgres_database_is_rejected(uri):
    with mock.patch.dict(os.environ, {"ADDRESSGUARD_TEST_ALLOW_SQLITE": ""}):
        with pytest.raises(RuntimeError, match="requires PostgreSQL"):
            _configure_database(_app(uri))


def test_postgres_gets_pooling_options():
    app = _app("postgresql://u:p@db.example/addressguard?sslmode=require")
    _configure_database(app)
    options = app.config["SQLALCHEMY_ENGINE_OPTIONS"]
    assert options["pool_pre_ping"] is True
    assert options["connect_args"]["connect_timeout"] == 10


def test_legacy_postgres_scheme_is_normalised():
    assert _database_url("postgres://u:p@h/db") == "postgresql://u:p@h/db"
    assert _database_url("'postgresql://u:p@h/db'") == "postgresql://u:p@h/db"


@pytest.mark.parametrize("system_resolves, probe_fails", [(False, False), (True, True)])
def test_public_dns_fallback_sets_hostaddr(system_resolves, probe_fails):
    import app as app_module
    flask_app = _app("postgresql://u:p@db.example/addressguard?sslmode=require")
    _configure_database(flask_app)
    with mock.patch.object(app_module, "system_can_resolve", return_value=system_resolves), \
            mock.patch.object(app_module, "_host_lookup_fails", return_value=probe_fails), \
            mock.patch.object(app_module, "resolve_via_public_dns", return_value="192.0.2.10"):
        assert app_module._apply_dns_fallback(flask_app) is True
    assert flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["hostaddr"] == "192.0.2.10"


def test_working_local_dns_needs_no_fallback():
    import app as app_module
    flask_app = _app("postgresql://u:p@db.example/addressguard?sslmode=require")
    _configure_database(flask_app)
    with mock.patch.object(app_module, "system_can_resolve", return_value=True), \
            mock.patch.object(app_module, "_host_lookup_fails", return_value=False):
        assert app_module._apply_dns_fallback(flask_app) is False
    assert "hostaddr" not in flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]


def test_unreachable_postgres_gives_a_clear_startup_error():
    with pytest.raises(RuntimeError, match="Cannot connect to PostgreSQL at no-such-host.invalid"):
        create_app({"SQLALCHEMY_DATABASE_URI": "postgresql://u:p@no-such-host.invalid/db"})
