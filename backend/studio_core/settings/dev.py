"""Settings DEV — overrides spécifiques au dev local."""

from celery.schedules import crontab

from .base import *

# Toujours True en dev, sauf override explicite via DJANGO_DEBUG
DEBUG = True

# Hosts raisonnables pour dev local
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]

# 🚫 Pas de redirection HTTPS en dev
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = None

# Cookies non "secure" en local
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
# CSRF double-submit en dev: cookie lisible par JS pour envoyer X-CSRFToken
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Debug Toolbar si installée
try:
    import debug_toolbar  # type: ignore  # noqa: F401

    if "debug_toolbar" not in INSTALLED_APPS:
        INSTALLED_APPS += ["debug_toolbar"]
    if "debug_toolbar.middleware.DebugToolbarMiddleware" not in MIDDLEWARE:
        MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
    INTERNAL_IPS = ["127.0.0.1"]
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────────────
# Celery (dev) — broker/result + planification beat de la purge e‑OTP
# ──────────────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

CELERY_BEAT_SCHEDULE = {
    "eotp_purge_every_min": {
        "task": "eotp.tasks.purge_expired",
        "schedule": crontab(minute="*/1"),
        "args": (),
    },
}
