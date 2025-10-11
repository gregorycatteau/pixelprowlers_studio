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
from ai_assistants.utils.agent_schema import (
    SCHEMA_VERSION,
    compute_manifest_hash,
    ensure_immutable_fields_unchanged,
    get_agent_schema,
    validate_agent_profile,
)
from django.core.management.base import BaseCommand, CommandError


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
            manifest = self._ensure_v21_manifest(data)
            self._normalize_manifest(manifest)
            errors = validate_agent_profile(manifest)
            if errors:
                pretty = "; ".join(errors[:5])
                raise CommandError(f"Schéma invalide pour {path.name}: {pretty}")
            slug = manifest["identity"]["slug"]

            existing = AgentProfile.objects.filter(slug=slug).first()
            if existing:
                immut_errors = ensure_immutable_fields_unchanged(
                    existing.manifest_json or {},
                    manifest,
                )
                if immut_errors:
                    joined = ", ".join(immut_errors)
                    raise CommandError(f"Champs immuables modifiés pour {path.name}: {joined}")

            defaults = self._build_defaults_from_manifest(manifest)
            obj, created = AgentProfile.objects.update_or_create(slug=slug, defaults=defaults)
            status = "Créé" if created else "MAJ"
            self.stdout.write(self.style.SUCCESS(f"✓ {status}: {obj.slug}"))

    @staticmethod
    def _ensure_v21_manifest(data: dict) -> dict:
        """
        Retourne un manifeste conforme v2.1.
        Si le JSON est déjà au format v2.1 (presence de identity/schema_version), on le renvoie tel quel.
        Pour le legacy (champ 'name'), on le transforme en manifeste minimal v2.1.
        """
        if "identity" in data and "schema_version" in data:
            manifest = {k: v for k, v in data.items() if k in get_agent_schema()["properties"]}
            return manifest

        name = data.get("name", "agent")
        slug = name.lower().replace(" ", "-")
        alias = data.get("alias") or name
        description = data.get("description", "")
        model = data.get("model", "gpt-4o")
        temperature = float(data.get("temperature", 0.4))
        instructions = data.get("instructions", "")
        communication = data.get("communication_style", {})

        return {
            "schema_version": SCHEMA_VERSION,
            "profile_version": "0.1.0",
            "identity": {
                "name": name,
                "slug": slug,
                "alias": alias,
                "description": description,
            },
            "governance": {
                "raison_d_etre": instructions or description or name,
                "missions": [description or "Mission non spécifiée"],
                "raci": {
                    "responsible": [alias],
                    "accountable": [],
                    "consulted": [],
                    "informed": [],
                },
                "decision_rights": {},
                "operating_modes": ["advisory"],
                "default_mode": "advisory",
            },
            "communication_style": {
                "tone": communication.get("tone", "Standard"),
                "sentence_length": communication.get("sentence_length", "moyenne"),
                "language_level": communication.get("language_level", "accessible-expert"),
                "metaphor_usage": communication.get("metaphor_usage", "modérée"),
                "emoji_usage": communication.get("emoji_usage", False),
                "disclaimers": communication.get("disclaimers", []),
            },
            "model_policy": {
                "provider_order": ["premium", "mid", "local"],
                "allowed_models": {
                    "premium": [model],
                    "mid": [],
                    "local": [],
                },
                "premium_unlock_required": True,
                "caps": {"daily_tokens_in": 200000, "daily_tokens_out": 200000},
                "latency_slo_ms": 8000,
                "retries": 1,
                "fallback": {"on_timeout": "mid", "on_policy_denied": "mid"},
                "rate_limits": {"rpm": 30, "rph": 1000},
                "cache_policy": {"enabled": False, "ttl_seconds": 0},
                "budget_policy": {
                    "max_eur_per_day": 3.0,
                    "hard_stop_on_exceed": True,
                    "exhaust_local_first": True,
                },
            },
            "security": {
                "data_minimization": True,
                "encryption_required": True,
                "anonymization_supported": True,
                "incident_alert_level": "medium",
                "sensitive_data_examples": data.get("security_protocol", {}),
            },
            "tools": data.get("tools", []),
            "observability": {
                "logs": {"fields": ["ts", "event"]},
                "metrics": ["requests"],
                "alarms": [],
                "audit_trail": {"enabled": False, "retention_days": 30},
            },
            "gates": {
                "preflight": [],
                "go_live": [],
                "rollback_plan": "disable agent",
            },
        }

    @staticmethod
    def _normalize_manifest(manifest: dict) -> None:
        integrations = manifest.get("integrations")
        if integrations:
            allowed_freq = {"daily", "weekly", "monthly", "never"}
            freq = integrations.get("data_sync_frequency")
            if freq and freq not in allowed_freq:
                integrations["data_sync_frequency"] = "daily"
        collab = manifest.get("collaboration_protocol")
        if collab:
            allowed_dev = {"low", "medium", "high"}
            level = collab.get("acceptable_deviation_level")
            if level and level not in allowed_dev:
                collab["acceptable_deviation_level"] = "medium"
        learning = manifest.get("learning")
        if learning:
            allowed_modes = {"manual_review", "auto", "off"}
            mode = learning.get("model_update_mode")
            if mode and mode not in allowed_modes:
                learning["model_update_mode"] = "manual_review"

        security = manifest.setdefault("security", {})
        security.pop("sensitive_data_examples", None)
        security.setdefault("forbidden_operations", ["write_secrets"])
        seclist = security.get("forbidden_operations", [])
        if not seclist:
            security["forbidden_operations"] = ["write_secrets"]
        security.setdefault("isolation_level", "sandboxed")
        security.setdefault("network_allowlist", [])

        gates = manifest.setdefault("gates", {})
        if not isinstance(gates.get("preflight"), list):
            gates["preflight"] = []
        if not isinstance(gates.get("go_live"), list):
            gates["go_live"] = []
        gates.setdefault("rollback_plan", "disable agent")

        observability = manifest.setdefault("observability", {})
        if "logs" not in observability or not isinstance(observability.get("logs"), dict):
            observability["logs"] = {"fields": ["ts", "event"]}
        else:
            observability["logs"].setdefault("fields", ["ts", "event"])
        observability.setdefault("metrics", ["requests"])
        observability.setdefault("alarms", [])
        if "audit_trail" not in observability or not isinstance(
            observability.get("audit_trail"), dict
        ):
            observability["audit_trail"] = {"enabled": False, "retention_days": 30}
        else:
            observability["audit_trail"].setdefault("enabled", False)
            observability["audit_trail"].setdefault("retention_days", 30)

        tools = manifest.setdefault("tools", [])
        if not tools:
            tools.append(
                {
                    "name": "code_interpreter",
                    "description": "Outil generique",
                    "parameters_schema": {"type": "object"},
                    "returns": "string",
                }
            )

        metadata = manifest.get("metadata")
        if isinstance(metadata, dict):
            allowed = {
                "owner",
                "squad",
                "budget_tier",
                "default_sensitivity",
                "created_at",
                "updated_at",
                "manifest_hash_sha256",
            }
            for key in list(metadata.keys()):
                if key not in allowed:
                    metadata.pop(key, None)

    @staticmethod
    def _build_defaults_from_manifest(manifest: dict) -> dict:
        identity = manifest["identity"]
        model = (
            manifest.get("runtime", {}).get("model")
            or (
                manifest.get("model_policy", {}).get("allowed_models", {}).get("premium") or [None]
            )[0]
            or (manifest.get("model_policy", {}).get("allowed_models", {}).get("mid") or [None])[0]
            or (manifest.get("model_policy", {}).get("allowed_models", {}).get("local") or [None])[
                0
            ]
            or "gpt-4o"
        )
        temperature = manifest.get("runtime", {}).get("temperature")
        comm = manifest.get("communication_style", {})

        return {
            "name": identity.get("name", identity["slug"]),
            "alias": identity.get("alias", ""),
            "description": identity.get("description", ""),
            "schema_version": manifest.get("schema_version", SCHEMA_VERSION),
            "profile_version": manifest.get("profile_version", "1.0.0"),
            "manifest_json": manifest,
            "manifest_hash_sha256": compute_manifest_hash(manifest),
            "model": model,
            "temperature": float(temperature if temperature is not None else 0.4),
            "communication_style": comm.get("tone", "Standard"),
            "is_active": manifest.get("metadata", {}).get("is_active", True),
        }
