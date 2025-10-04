# backend/overall_context/vectorizer/tasks.py
# -*- coding: utf-8 -*-
"""
Tâches Celery de vectorisation de zones CDN.
- Isoler les workloads CPU/IO pour éviter de bloquer le process web.
- Utiliser la queue 'vectorizer' (définie dans settings.prod).
"""

from __future__ import annotations

from typing import Dict, List

from celery import shared_task

from ..utils.context_loader import load_zone_file  # charge un JSON de zone
from .vectorize_chunks import vectorize_file  # fonction existante


@shared_task(name="overall_context.vectorizer.tasks.vectorize_zone")
def vectorize_zone(zone_id: str) -> Dict[str, int]:
    """
    Vectorise une zone CDN complète.
    :param zone_id: Identifiant de la zone (ex: 'Z1')
    :return: { "processed": <int> }
    """
    data = load_zone_file(zone_id)
    # On s'attend à un schéma avec "chunks": [{"path": "..."}]
    files: List[str] = [c["path"] for c in data.get("chunks", []) if "path" in c]
    processed = 0
    for fpath in files:
        try:
            vectorize_file(fpath)
            processed += 1
        except Exception as exc:
            # TODO: log structuré + métriques
            print(f"[vectorizer] Erreur sur {fpath}: {exc}")
    return {"processed": processed}
