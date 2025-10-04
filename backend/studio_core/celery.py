# backend/studio_core/celery.py
# -*- coding: utf-8 -*-
"""
Configuration Celery pour PixelProwlers Studio.
- Lit la config dans Django settings (namespace CELERY)
- Auto-discovery des tâches dans toutes les apps installées
"""

import os

from celery import Celery

# ⚠️ En production, cette variable est surchargée par l'env du worker
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studio_core.settings.prod")

app = Celery("studio_core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def health(self) -> str:
    """Vérifie que le worker répond correctement."""
    return "ok"
