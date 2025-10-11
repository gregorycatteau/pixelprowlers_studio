"""Settings TEST — pour pytest/CI."""

import os

from studio_core.dbconf import build_database_settings

from .base import *  # noqa

DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = build_database_settings(BASE_DIR, MERGED_ENV)
for db in DATABASES.values():
    db["CONN_MAX_AGE"] = 0
    db["ATOMIC_REQUESTS"] = False
