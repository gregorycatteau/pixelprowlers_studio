"""
Django settings for studio_core project.
Base agnostique d'environnement avec chargement .env et fallback sûrs.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import List

# ──────────────────────────────────────────────────────────────────────────────
# Détection robuste de BASE_DIR (répertoire "backend")
# ──────────────────────────────────────────────────────────────────────────────
_THIS_FILE = Path(__file__).resolve()
if _THIS_FILE.parent.name == "settings":
    STUDIO_CORE_DIR = _THIS_FILE.parent.parent  # .../studio_core
    BASE_DIR = STUDIO_CORE_DIR.parent  # .../backend
else:
    STUDIO_CORE_DIR = _THIS_FILE.parent  # .../studio_core
    BASE_DIR = STUDIO_CORE_DIR.parent  # .../backend

# ──────────────────────────────────────────────────────────────────────────────
# Chargement .env (commun + spécifique à APP_ENV)
# ──────────────────────────────────────────────────────────────────────────────
try:
    import environ  # type: ignore
except Exception:
    environ = None


def env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _read_env_file(path: Path, overwrite: bool = False) -> None:
    """Lit un fichier .env s’il existe (silencieux)."""
    if environ and path.exists():
        try:
            environ.Env.read_env(str(path), overwrite=overwrite)
        except Exception:
            # on ignore volontairement pour ne pas casser le boot
            pass


# Valeur initiale puis .env commun
APP_ENV: str = os.getenv("APP_ENV", "dev").strip().lower()
_read_env_file(BASE_DIR / ".env", overwrite=False)

# .env spécifique (peut redéfinir APP_ENV & co)
APP_ENV = os.getenv("APP_ENV", APP_ENV).strip().lower()
_read_env_file(BASE_DIR / f".env.{APP_ENV}", overwrite=True)


def _env_list(key: str, default: List[str] | None = None) -> List[str]:
    """Convertit 'a,b,c' → ['a','b','c']."""
    raw = os.getenv(key, "")
    if not raw:
        return default or []
    return [x.strip() for x in raw.split(",") if x.strip()]


# ──────────────────────────────────────────────────────────────────────────────
# Clé / Debug
# ──────────────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", default=(APP_ENV != "prod"))

# ──────────────────────────────────────────────────────────────────────────────
# Allowed hosts / CSRF / CORS
# ──────────────────────────────────────────────────────────────────────────────
ALLOWED_HOSTS: List[str] = _env_list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Valeurs par défaut compatibles Nuxt (overridable par env)
_DEFAULT_TRUSTED = [
    "http://localhost:3000",
    "https://localhost:3000",
    "https://studio.pixelprowlers.io",
]
CSRF_TRUSTED_ORIGINS: List[str] = list(
    {*_DEFAULT_TRUSTED, *set(_env_list("DJANGO_CSRF_TRUSTED_ORIGINS", []))}
)

# ──────────────────────────────────────────────────────────────────────────────
# Apps
# ──────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # champs ArrayField, etc.
    # API
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    # GraphQL
    "strawberry.django",
    "strawberry_django",
    # Apps projet
    "accounts.apps.AccountsConfig",
    "ai_assistants.apps.AiAssistantsConfig",  # ← AJOUT
    "overall_context",  # ← (optionnel) si tu l’emploies
    "api",
]

# Optionally include API app skeleton if present (safe import)
try:
    import api  # type: ignore  # noqa: F401

    INSTALLED_APPS.append("api")
except Exception:
    pass

# CORS (si présent)
try:
    import corsheaders  # type: ignore  # noqa: F401

    INSTALLED_APPS.append("corsheaders")
    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

# Ratelimit optionnel si installé
try:
    import ratelimit  # type: ignore  # noqa: F401

    INSTALLED_APPS.append("ratelimit")
    _HAS_RATELIMIT = True
except Exception:
    _HAS_RATELIMIT = False

# DRF — OpenAPI schema via drf-spectacular
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *(["corsheaders.middleware.CorsMiddleware"] if _HAS_CORS else []),
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 🔎 Request-ID + Audit JWT (IP, UA, jti, scopes…)
    "accounts.middleware.RequestIDAndAuditMiddleware",
    "studio_core.api_auth_middleware.ApiAuthRedirectTo401Middleware",
    "studio_core.gates_middleware.GatedSessionMiddleware",
]

ROOT_URLCONF = "studio_core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "studio_core.wsgi.application"

# ──────────────────────────────────────────────────────────────────────────────
# DB (DATABASE_URL → dict) avec fallback SQLite sécurisé
# ──────────────────────────────────────────────────────────────────────────────
from dj_database_url import config as dj_db_config  # type: ignore

_database_url = (os.getenv("DATABASE_URL") or "").strip()


def _build_db_config() -> dict:
    """Construit DATABASES['default'] depuis DATABASE_URL, fallback SQLite si besoin."""
    ssl_req = APP_ENV == "prod"
    db: dict = {}
    if _database_url:
        try:
            db = dj_db_config(default=_database_url, conn_max_age=60, ssl_require=ssl_req) or {}
        except Exception:
            db = {}
    if not db or "ENGINE" not in db:
        db = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    return db


DATABASES = {"default": _build_db_config()}

# ──────────────────────────────────────────────────────────────────────────────
# DRF — JWT + Throttling
# ──────────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("DRF_THROTTLE_ANON", "30/min"),
        "user": os.getenv("DRF_THROTTLE_USER", "120/min"),
        "jwt_obtain": os.getenv("DRF_THROTTLE_JWT_OBTAIN", "10/min"),
        "jwt_refresh": os.getenv("DRF_THROTTLE_JWT_REFRESH", "30/min"),
        "jwt_verify": os.getenv("DRF_THROTTLE_JWT_VERIFY", "60/min"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --- SimpleJWT (RS256 si clés fournies, sinon fallback HS256) ---
JWT_PRIVATE_KEY = os.environ.get("JWT_PRIVATE_KEY", "").strip()
JWT_PUBLIC_KEY = os.environ.get("JWT_PUBLIC_KEY", "").strip()

if JWT_PRIVATE_KEY and JWT_PUBLIC_KEY:
    SIMPLE_JWT = {
        "ALGORITHM": "RS256",
        "SIGNING_KEY": JWT_PRIVATE_KEY,
        "VERIFYING_KEY": JWT_PUBLIC_KEY,
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "UPDATE_LAST_LOGIN": True,
        "TOKEN_OBTAIN_SERIALIZER": "accounts.auth.PPTokenObtainPairSerializer",
    }
else:
    # Fallback Dev : HS256 via SECRET_KEY (ne pas utiliser en prod)
    SIMPLE_JWT = {
        "ALGORITHM": "HS256",
        "SIGNING_KEY": SECRET_KEY,
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "AUTH_HEADER_TYPES": ("Bearer",),
        "UPDATE_LAST_LOGIN": True,
        "TOKEN_OBTAIN_SERIALIZER": "accounts.auth.PPTokenObtainPairSerializer",
    }

# --- GraphQL toggles (lus par SecureGraphQLView) ---
GRAPHQL_MAX_DEPTH = int(os.getenv("GRAPHQL_MAX_DEPTH", "8"))
GRAPHQL_REQUIRE_OPERATION_NAME = os.getenv(
    "GRAPHQL_REQUIRE_OPERATION_NAME",
    "false" if DEBUG else "true",
).lower() in ("1", "true", "yes")
GRAPHQL_RATE = os.getenv("GRAPHQL_RATE", "")  # ex: "60/m" si django-ratelimit présent

# ──────────────────────────────────────────────────────────────────────────────
# Password validators
# ──────────────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ──────────────────────────────────────────────────────────────────────────────
# I18N
# ──────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = os.getenv("DJANGO_LANGUAGE_CODE", "fr-fr")
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Europe/Paris")
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────────────────────────────────────
# Static & media
# ──────────────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATICFILES_DIRS = [str(BASE_DIR / "static")] if (BASE_DIR / "static").exists() else []

STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = str(BASE_DIR / "media")

# ──────────────────────────────────────────────────────────────────────────────
# Sécurité prod + cookies
# ──────────────────────────────────────────────────────────────────────────────
if APP_ENV == "prod":
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)

    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    # En dev: laissons-overridable (utile si tu es en HTTP local)
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ──────────────────────────────────────────────────────────────────────────────
# CORS (activé si corsheaders présent)
# ──────────────────────────────────────────────────────────────────────────────
if "corsheaders" in INSTALLED_APPS:
    CORS_ALLOWED_ORIGINS: List[str] = list(
        {*_DEFAULT_TRUSTED, *set(_env_list("CORS_ALLOWED_ORIGINS", []))}
    )
    CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", True)

# ──────────────────────────────────────────────────────────────────────────────
# Cookies par défaut (cohérents avec Nuxt + refresh HttpOnly)
# ──────────────────────────────────────────────────────────────────────────────
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# ──────────────────────────────────────────────────────────────────────────────
# Logging console
# ──────────────────────────────────────────────────────────────────────────────
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}:{lineno} — {message}", "style": "{"},
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": DJANGO_LOG_LEVEL},
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": os.getenv("SQL_LOG_LEVEL", "WARNING"),
        },
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
