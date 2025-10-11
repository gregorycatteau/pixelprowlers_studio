"""Runtime helpers to build Django DATABASES from environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Mapping, MutableMapping

import dj_database_url

logger = logging.getLogger("studio_core.db")

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _config_from_url(
    url: str,
    conn_max_age: int,
    atomic_requests: bool,
    ssl_required: bool,
) -> MutableMapping[str, object]:
    config = dj_database_url.parse(url, conn_max_age=conn_max_age, ssl_require=ssl_required) or {}
    config.setdefault("CONN_MAX_AGE", conn_max_age)
    config.setdefault("ATOMIC_REQUESTS", atomic_requests)
    return config


def _config_from_components(
    *,
    engine: str,
    name: str,
    user: str,
    password: str,
    host: str,
    port: str,
    conn_max_age: int,
    atomic_requests: bool,
) -> MutableMapping[str, object]:
    return {
        "ENGINE": engine,
        "NAME": name,
        "USER": user,
        "PASSWORD": password,
        "HOST": host,
        "PORT": port,
        "CONN_MAX_AGE": conn_max_age,
        "ATOMIC_REQUESTS": atomic_requests,
    }


def build_database_settings(base_dir: Path, env: Mapping[str, str] | None = None) -> dict:
    """Construct DATABASES from environment variables with sane fallbacks."""

    env = env or os.environ
    app_env = env.get("APP_ENV", "dev").strip().lower()
    conn_max_age = _as_int(env.get("DB_CONN_MAX_AGE"), 60)
    atomic_requests = _as_bool(env.get("DB_ATOMIC_REQUESTS"), app_env != "prod")
    ssl_required = _as_bool(env.get("DB_SSL_REQUIRE"), app_env == "prod")

    database_url = (env.get("DATABASE_URL") or "").strip()
    if database_url:
        config = _config_from_url(database_url, conn_max_age, atomic_requests, ssl_required)
        return {"default": config}

    host = (env.get("DB_HOST") or "").strip()
    name = (env.get("DB_NAME") or "").strip()
    user = (env.get("DB_USER") or "").strip()
    password = (env.get("DB_PASSWORD") or "").strip()
    port = (env.get("DB_PORT") or "5432").strip()
    if all([host, name, user, password]):
        engine = (env.get("DB_ENGINE") or "django.db.backends.postgresql").strip()
        config = _config_from_components(
            engine=engine,
            name=name,
            user=user,
            password=password,
            host=host,
            port=port,
            conn_max_age=conn_max_age,
            atomic_requests=atomic_requests,
        )
        return {"default": config}

    fallback_url = (env.get("FALLBACK_DATABASE_URL") or "").strip()
    if fallback_url:
        config = _config_from_url(fallback_url, conn_max_age, atomic_requests, ssl_required)
        return {"default": config}

    sqlite_path = base_dir / "db.sqlite3"
    logger.warning(
        "No database environment variables supplied; falling back to SQLite at %s", sqlite_path
    )
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(sqlite_path),
            "CONN_MAX_AGE": conn_max_age,
            "ATOMIC_REQUESTS": atomic_requests,
        }
    }


def describe_db_connection(config: Mapping[str, object]) -> str:
    """Return a redacted string describing the target database."""
    engine = config.get("ENGINE", "")
    if engine == "django.db.backends.sqlite3":
        return f"sqlite:///{config.get('NAME')}"

    host = config.get("HOST") or "localhost"
    port = config.get("PORT") or "5432"
    name = config.get("NAME") or ""
    return f"{engine}:{host}:{port}/{name}"
