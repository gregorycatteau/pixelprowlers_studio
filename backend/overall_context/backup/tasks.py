# backend/overall_context/backup/tasks.py
# -*- coding: utf-8 -*-
"""
Tâches Celery pour la sauvegarde/restauration/rotation du CDN contextuel.
- Queue dédiée 'backup'
- Chaque tâche est isolée pour être chaînable (beat, workflow, etc.)
"""

from __future__ import annotations

from celery import shared_task

from ..validators.post_restore_validator import post_restore_validate
from .backup_encryptor import run_backup as run_backup_encryptor
from .rotate_backups import rotate_backups as run_rotation


@shared_task(name="overall_context.backup.tasks.run_backup")
def run_backup() -> str:
    """Exécute une sauvegarde chiffrée du CDN."""
    # TODO: paramétrer des chemins via settings/env si nécessaire
    ok = run_backup_encryptor()
    return "ok" if ok else "error"


@shared_task(name="overall_context.backup.tasks.rotate")
def rotate() -> str:
    """Applique la politique de rotation des sauvegardes."""
    ok = run_rotation()
    return "ok" if ok else "error"


@shared_task(name="overall_context.backup.tasks.restore_and_validate")
def restore_and_validate(archive_path: str) -> str:
    """
    Restaure un backup donné puis valide l'intégrité post-restauration.
    :param archive_path: chemin du .bin/.enc à restaurer
    """
    # NOTE: on suppose que restore_decryptor est appelé par ailleurs
    # Ici, on enchaîne surtout la validation post-restore.
    try:
        post_restore_validate()
        return "ok"
    except Exception as exc:
        print(f"[backup] post-restore validation error: {exc}")
        return "error"
