# backend/ai_assistants/signals.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AgentProfile
from .utils.agent_schema import SCHEMA_VERSION, compute_manifest_hash

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AgentProfile)
def sync_manifest_hash(sender, instance: AgentProfile, created, **kwargs):
    """
    À chaque sauvegarde d'un AgentProfile :
    - recalcule le hash du manifeste,
    - l'injecte dans la colonne 'manifest_hash_sha256' ET dans manifest_json.metadata.manifest_hash_sha256,
    - journalise un warning si schema_version ≠ attendu.
    """
    manifest = dict(instance.manifest_json or {})
    meta = dict(manifest.get("metadata") or {})
    computed = compute_manifest_hash(manifest)

    need_update = False
    if instance.manifest_hash_sha256 != computed:
        need_update = True
    if meta.get("manifest_hash_sha256") != computed:
        meta["manifest_hash_sha256"] = computed
        manifest["metadata"] = meta
        need_update = True

    if need_update:
        # update() pour éviter une boucle de signaux
        AgentProfile.objects.filter(pk=instance.pk).update(
            manifest_hash_sha256=computed, manifest_json=manifest
        )
        logger.info("AgentProfile[%s]: manifest hash synchronisé.", instance.slug)

    # Surveille les dérives de version de schéma (utile en local)
    if (manifest.get("schema_version") or "") != SCHEMA_VERSION:
        logger.warning(
            "AgentProfile[%s]: schema_version=%s (attendu=%s).",
            instance.slug,
            manifest.get("schema_version"),
            SCHEMA_VERSION,
        )
