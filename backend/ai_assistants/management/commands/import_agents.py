# backend/ai_assistants/management/commands/import_agents.py
# -*- coding: utf-8 -*-
"""
Commande Django : importe les JSON d'agents après validation schéma.
Usage: python manage.py import_agents --dir backend/agents
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_assistants.models import AgentProfile
from ai_assistants.utils.agent_schema import AGENT_SCHEMA
from django.core.management.base import BaseCommand, CommandError
from jsonschema import ValidationError, validate


class Command(BaseCommand):
    help = "Importe/Met à jour les profils d'agents depuis des JSON, avec validation stricte."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir", default="backend/agents", help="Répertoire des fichiers *_agent.json"
        )

    def handle(self, *args, **opts):
        root = Path(opts["dir"]).resolve()
        if not root.exists():
            raise CommandError(f"Répertoire introuvable: {root}")

        files = sorted(root.glob("*_agent.json"))
        if not files:
            self.stdout.write(self.style.WARNING(f"Aucun *_agent.json trouvé dans {root}"))
            return

        for path in files:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            try:
                validate(instance=data, schema=AGENT_SCHEMA)
            except ValidationError as e:
                raise CommandError(f"Schéma invalide pour {path.name}: {e.message}") from e

            obj, _created = AgentProfile.objects.update_or_create(
                name=data["name"],
                defaults={
                    "description": data.get("description", ""),
                    "model": data["model"],
                    "temperature": data["temperature"],
                    "instructions": data["instructions"],
                    "metadata": data,  # garde la source JSON complète
                },
            )
            self.stdout.write(self.style.SUCCESS(f"✓ Importé/MAJ: {obj.name}"))
