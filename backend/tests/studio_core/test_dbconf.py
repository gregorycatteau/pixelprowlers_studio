from pathlib import Path

import pytest
from studio_core import dbconf


@pytest.mark.unit
def test_build_from_database_url(tmp_path):
    env = {
        "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/app",
        "APP_ENV": "dev",
    }
    databases = dbconf.build_database_settings(tmp_path, env)
    config = databases["default"]
    assert config["NAME"] == "app"
    assert config["USER"] == "user"
    assert config["HOST"] == "db.example.com"
    assert config["CONN_MAX_AGE"] == 60
    assert config["ATOMIC_REQUESTS"] is True


@pytest.mark.unit
def test_build_from_components(tmp_path):
    env = {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "5432",
        "DB_NAME": "pxp_dev",
        "DB_USER": "striker_dev",
        "DB_PASSWORD": "secret",
        "DB_CONN_MAX_AGE": "120",
        "DB_ATOMIC_REQUESTS": "false",
    }
    databases = dbconf.build_database_settings(tmp_path, env)
    config = databases["default"]
    assert config["PORT"] == "5432"
    assert config["CONN_MAX_AGE"] == 120
    assert config["ATOMIC_REQUESTS"] is False


@pytest.mark.unit
def test_fallback_to_sqlite(tmp_path, caplog):
    databases = dbconf.build_database_settings(tmp_path, {})
    config = databases["default"]
    assert config["ENGINE"] == "django.db.backends.sqlite3"
    assert Path(config["NAME"]).name == "db.sqlite3"
    assert dbconf.describe_db_connection(config).startswith("sqlite:///")
