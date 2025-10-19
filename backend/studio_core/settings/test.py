"""Settings TEST — pour pytest/CI."""

import os

from studio_core.dbconf import build_database_settings

from .base import *  # noqa

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0"]

# Allow Playwright-in-Docker to access frontend/back via host.docker.internal:3100/8100
CSRF_TRUSTED_ORIGINS = list(
    sorted(
        set(
            (globals().get("CSRF_TRUSTED_ORIGINS") or [])
            + [
                "http://localhost:3100",
                "http://127.0.0.1:3100",
                "http://host.docker.internal:3100",
            ]
        )
    )
)

# CORS is only applied if corsheaders is installed (handled in base.py)
try:
    CORS_ALLOWED_ORIGINS = list(
        sorted(
            set(
                (globals().get("CORS_ALLOWED_ORIGINS") or [])
                + [
                    "http://localhost:3100",
                    "http://127.0.0.1:3100",
                    "http://host.docker.internal:3100",
                ]
            )
        )
    )
except Exception:
    pass

# URLConf minimal pour les tests e-OTP (évite l'import de admin/accounts models)
ROOT_URLCONF = "studio_core.test_urls_eotp"
# LOGIN_URL en chemin absolu (pas de reverse nécessaire dans le middleware)
LOGIN_URL = "/api/auth/login/"
# Assouplir le CSRF en test pour header X-CSRFToken (double-submit simulé)
CSRF_COOKIE_HTTPONLY = False
# Désactiver tout ratelimit en tests E2E (évite les 403 Ratelimited)
RATELIMIT_ENABLE = False
# Paramétrage e-OTP pour tests: TTL court, 3 essais, cooldown court, code 6 chiffres
os.environ.setdefault("EOTP_TTL", "5")  # secondes
os.environ.setdefault("EOTP_MAX_TRIES", "3")
os.environ.setdefault("COOLDOWN_SECONDS", "2")
os.environ.setdefault("EOTP_CODE_LENGTH", "6")
os.environ.setdefault("EOTP_STRICT_CONTEXT", "0")

# Par défaut, forcer SQLite pour les tests (évite la création d'une DB Postgres).
# Pour utiliser Postgres en CI si nécessaire, définir TEST_USE_POSTGRES=1.
if os.getenv("TEST_USE_POSTGRES", "").strip().lower() in ("1", "true", "yes", "on"):
    DATABASES = build_database_settings(BASE_DIR, MERGED_ENV)
    for db in DATABASES.values():
        db["CONN_MAX_AGE"] = 0
        db["ATOMIC_REQUESTS"] = False
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "test_db.sqlite3"),
            "CONN_MAX_AGE": 0,
            "ATOMIC_REQUESTS": False,
        }
    }

# En environnement de test sous SQLite, exclure l'app 'accounts' (ArrayField Postgres-only)
try:
    if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
        EXCLUDE_APPS = {
            "accounts.apps.AccountsConfig",  # uses Postgres ArrayField
            "ai_assistants.apps.AiAssistantsConfig",  # contains raw SQL incompatible with SQLite
        }
        INSTALLED_APPS = [a for a in INSTALLED_APPS if a not in EXCLUDE_APPS]
        # Retire le middleware qui importe accounts.models (non installé en test SQLite)
        MIDDLEWARE = [
            m for m in MIDDLEWARE if m != "accounts.middleware.RequestIDAndAuditMiddleware"
        ]
except Exception:
    pass
