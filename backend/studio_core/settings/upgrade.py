"""Settings UPGRADE — tests de migration/montée de version avec sécu renforcée."""

from datetime import timedelta

from .base import *

DEBUG = False
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]

# Rate-limit des tentatives d'auth pour tes tests “chacal”
if "axes" not in INSTALLED_APPS:
    INSTALLED_APPS += ["axes"]

# On place Axes tôt (après Security + WhiteNoise)
# MIDDLEWARE de base: [Security, WhiteNoise, ...]
if "axes.middleware.AxesMiddleware" not in MIDDLEWARE:
    MIDDLEWARE = MIDDLEWARE[:2] + ["axes.middleware.AxesMiddleware"] + MIDDLEWARE[2:]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Paramètres Axes (ajuste selon tes besoins)
AXES_ENABLED = True
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = timedelta(hours=int(os.getenv("AXES_COOLOFF_HOURS", "1")))
AXES_ONLY_USER_FAILURES = True
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
