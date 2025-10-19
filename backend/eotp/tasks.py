# -*- coding: utf-8 -*-
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command


@shared_task(name="eotp.tasks.purge_expired")
def purge_expired(dry_run: bool = False) -> str:
    """
    Tâche Celery: exécute la purge TTL des challenges e-OTP.
    - En dev/test, planifiée via Celery beat (voir settings CELERY_BEAT_SCHEDULE).
    - En prod, activer selon la stratégie d'exploitation.
    """
    args = ["--dry-run"] if dry_run else []
    call_command("eotp_purge_expired", *args)
    return f"eotp_purge_expired(dry_run={dry_run}) executed"
