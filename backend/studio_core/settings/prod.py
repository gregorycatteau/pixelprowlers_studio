# backend/studio_core/settings/prod.py
# -*- coding: utf-8 -*-
"""
Paramètres PRODUCTION pour PixelProwlers Studio.
- Surcharge base.py
- Charge le durcissement security.py
- Ajoute Celery, CSP, logs
"""

import os

from .base import *  # noqa

# --- Mode & hôtes ---
DEBUG = False
ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS", os.getenv("DJANGO_ALLOWED_HOSTS", "pixelprowlers.io,studio.pixelprowlers.io")
).split(",")
CSRF_TRUSTED_ORIGINS = [
    *[
        o.strip()
        for o in os.getenv(
            "CSRF_TRUSTED_ORIGINS", os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
        ).split(",")
        if o.strip()
    ],
]

# --- Clé secrète ---
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 64 or SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError("SECRET_KEY trop faible pour la production.")

# --- Import durcissement ---
from .security import *  # noqa

# --- DB obligatoire en prod ---
if "DATABASE_URL" not in os.environ:
    raise RuntimeError("DATABASE_URL manquante en production.")

# --- CORS (prod : domaines stricts) ---
if "corsheaders" in INSTALLED_APPS:
    CORS_ALLOWED_ORIGINS = [
        o for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
    CORS_ALLOW_CREDENTIALS = True

# --- Celery (queues dédiées vectorizer/backup) ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "900"))  # 15 min hard
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "480"))  # 8 min soft
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "200"))
CELERY_TASK_ALWAYS_EAGER = False  # jamais en prod
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = {
    "default": {},
    "vectorizer": {},
    "backup": {},
}
CELERY_TASK_ROUTES = {
    "overall_context.vectorizer.tasks.*": {"queue": "vectorizer"},
    "overall_context.backup.tasks.*": {"queue": "backup"},
}

# --- CSP (Content Security Policy) via django-csp ---
# On active django-csp uniquement en prod pour XSS hardening
try:
    import csp  # type: ignore  # noqa

    if "csp" not in INSTALLED_APPS:
        INSTALLED_APPS.append("csp")
    if "csp.middleware.CSPMiddleware" not in MIDDLEWARE:
        # placer APRES SecurityMiddleware et AVANT CommonMiddleware si possible
        MIDDLEWARE.insert(1, "csp.middleware.CSPMiddleware")
except Exception:
    pass

# Politique CSP prudente (adapter si inline scripts nécessaires → nonces)
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)  # pas de 'unsafe-inline' en prod
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")  # tolérance pour CSS inlined, à réduire plus tard
CSP_IMG_SRC = ("'self'", "data:")
CSP_CONNECT_SRC = ("'self'",)
CSP_FONT_SRC = ("'self'", "data:")
CSP_FRAME_ANCESTORS = ("'none'",)

# --- Logs ---
LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "std"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {
            "handlers": ["console"],
            "level": os.getenv("SQL_LOG_LEVEL", "WARNING"),
        },
    },
}
