# -*- coding: utf-8 -*-
"""
Migration des profils agents "legacy" (style OpenAI Assistants) vers le schéma PixelProwlers v2.1.

Usage:
  python agents/tools/migrate_legacy_profiles.py <src_dir> <dst_dir>

- Lit tous les *.json de <src_dir>
- Génère des profils v2.1 dans <dst_dir>, sans écraser les originaux
- Met des valeurs par défaut raisonnables pour satisfaire le schéma v2.1
- Conserve un maximum d'infos ("instructions", "tools", "security_protocol", etc.)

Sécurité:
- Pas de secrets manipulés ici.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "2.1.0"


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "agent"


def map_model_to_tier_and_name(model: str) -> tuple[str, str]:
    """Mappe grossièrement un nom de modèle vers un 'tier' et un identifiant modèle."""
    m = (model or "").lower()
    # Ajuste ici si besoin (ex: "gpt-5" ➜ premium)
    if any(k in m for k in ["gpt-4", "gpt-5", "o3", "sonnet", "opus"]):
        return "premium", model
    if any(k in m for k in ["gpt-3.5", "haiku", "small"]):
        return "mid", model
    return "local", model or "local-llm"


def convert_tools(legacy_tools: list[dict]) -> list[dict]:
    """Convertit la liste 'tools' legacy vers la structure v2.1 (name/description/parameters_schema/returns...)."""
    out: list[dict] = []
    for t in legacy_tools or []:
        ttype = t.get("type")
        if ttype == "function":
            fn = t.get("function", {})
            out.append(
                {
                    "name": fn.get("name", "fn"),
                    "description": fn.get("description", "fonction outil"),
                    "parameters_schema": fn.get("parameters", {"type": "object"}),
                    "returns": "string",
                    "scopes": ["dev", "test", "prod"],
                    "audit": {"enabled": True, "redact_inputs": True},
                }
            )
        elif ttype in ("code_interpreter", "file_search"):
            out.append(
                {
                    "name": ttype,
                    "description": f"Outil {ttype} hérité",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "returns": "string",
                    "scopes": ["dev", "test"],
                    "audit": {"enabled": True, "redact_inputs": True},
                }
            )
        else:
            # inconnu => on stocke générique
            out.append(
                {
                    "name": ttype or "tool",
                    "description": "Outil hérité (générique)",
                    "parameters_schema": {"type": "object"},
                    "returns": "string",
                    "scopes": ["dev", "test"],
                    "audit": {"enabled": True, "redact_inputs": True},
                }
            )
    if not out:
        # schéma v2.1 : au moins 1 tool requis
        out.append(
            {
                "name": "noop",
                "description": "Outil neutre",
                "parameters_schema": {"type": "object"},
                "returns": "string",
                "scopes": ["dev", "test"],
                "audit": {"enabled": True, "redact_inputs": True},
            }
        )
    return out


def migrate_one(data: dict) -> dict:
    name = data.get("name", "Agent")
    desc = data.get("description", "")
    slug = slugify(name)
    model = data.get("model", "")
    tier, model_name = map_model_to_tier_and_name(model)

    # communication_style (legacy) ➜ v2.1
    comm = data.get("communication_style", {})
    tone = comm.get("tone", "professionnel")
    sentence_length = comm.get("sentence_length", "moyenne")
    language_level = comm.get("language_level", "accessible-expert")
    metaphor_usage = comm.get("metaphor_usage", "modérée")
    emoji_usage = bool(comm.get("emoji_usage", False))

    # security_protocol (legacy) ➜ v2.1
    sec_legacy = data.get("security_protocol", {})
    incident = sec_legacy.get("incident_alert_level", "medium")

    # context/integrations/learning/collaboration
    context_enrichment = data.get("context_enrichment", {})
    integrations = data.get("integrations", {})
    learning = data.get("learning_protocol", {})
    collab = data.get("collaboration_protocol", {})

    now = datetime.now(timezone.utc).isoformat()

    v21 = {
        "schema_version": SCHEMA_VERSION,
        "profile_version": "1.0.0",
        "identity": {
            "name": name,
            "slug": slug,
            "alias": data.get("alias", name),
            "description": desc,
        },
        "governance": {
            "raison_d_etre": f"Agent {name} — profil migré (legacy➜v2.1).",
            "missions": ["Voir description"],
            "raci": {
                "responsible": [name],
                "accountable": ["Jared"],
                "consulted": [],
                "informed": [],
            },
            "decision_rights": {},
            "operating_modes": ["advisory", "dry_run"],
            "default_mode": "advisory",
        },
        "communication_style": {
            "tone": tone,
            "sentence_length": (
                sentence_length if sentence_length in ("courte", "moyenne", "longue") else "moyenne"
            ),
            "language_level": (
                language_level
                if language_level in ("débutant", "accessible-expert", "expert")
                else "accessible-expert"
            ),
            "metaphor_usage": (
                metaphor_usage if metaphor_usage in ("faible", "modérée", "élevée") else "modérée"
            ),
            "emoji_usage": emoji_usage,
            "disclaimers": [],
        },
        "model_policy": {
            "provider_order": (
                ["premium", "mid", "local"] if tier == "premium" else ["mid", "local", "premium"]
            ),
            "allowed_models": {
                "local": [],
                "mid": [],
                "premium": [model_name] if tier == "premium" else [],
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
            "data_minimization": bool(sec_legacy.get("data_minimization", True)),
            "encryption_required": bool(sec_legacy.get("encryption_required", True)),
            "anonymization_supported": bool(sec_legacy.get("anonymization_supported", True)),
            "incident_alert_level": (
                incident if incident in ("low", "medium", "high", "critical") else "medium"
            ),
            "threat_model": ["injections", "exfiltration", "dos", "secrets_leak"],
            "pii_allowed": {"classes": ["email"], "storage_rules": "hashed_or_encrypted"},
            "secrets_scope": ["runtime_env"],
            "network_allowlist": [],
            "forbidden_operations": ["write_secrets", "expose_pii", "change_ci"],
            "isolation_level": "sandboxed",
        },
        "context": {
            "sources": {
                "nextcloud_paths": [],
                "wiki_pages": [],
                "apis": [],
            },
            "retrieval": {
                "rag_enabled": False,
                "retriever": "keyword",
                "top_k": 5,
                "max_context_tokens": 4000,
                "citation_required": False,
                "freshness_max_days": 365,
            },
            "privacy_filters": [],
        },
        "integrations": {
            "crm_systems": integrations.get("crm_systems", []),
            "data_sync_frequency": integrations.get("data_sync_frequency", "weekly"),
            "webhooks_supported": bool(integrations.get("webhooks_supported", True)),
            "email_platforms": integrations.get("email_platforms", []),
            "analytics": integrations.get("analytics", []),
        },
        "learning": {
            "model_update_mode": learning.get("model_update_mode", "manual_review"),
            "continuous_learning": bool(learning.get("continuous_learning", True)),
            "source_feedback": learning.get("source_feedback", []),
            "evaluation": {
                "offline_datasets": [],
                "rubrics": [],
                "schedule": "",
                "quality_targets": [],
            },
        },
        "collaboration_protocol": {
            "preferred_partners": collab.get("preferred_partners", []),
            "handoff_expectation": collab.get("handoff_expectation", "documenté"),
            "collaboration_style": collab.get("collaboration_style", "asynchrone"),
            "acceptable_deviation_level": collab.get("acceptable_deviation_level", "medium"),
        },
        "compliance": {
            "gdpr": {"dpa_signed": False, "data_retention_days": 365, "dsar_supported": True},
            "consent_required": True,
            "logging_minimization": True,
        },
        "observability": {
            "logs": {"fields": ["ts", "agent", "event", "status"]},
            "metrics": ["requests", "latency_ms", "tokens_in", "tokens_out", "errors"],
            "alarms": ["budget_exceeded", "secrets_leak", "too_many_errors"],
            "audit_trail": {"enabled": True, "retention_days": 365},
        },
        "gates": {
            "preflight": ["schema_validate", "security_review", "budget_check"],
            "go_live": ["tests_pass", "owner_approval"],
            "rollback_plan": "disable_agent + revert profile_version; notify owner",
        },
        "tools": convert_tools(data.get("tools", [])),
        "immutable_fields": ["identity.name", "identity.slug", "tools[].name"],
        "metadata": {
            "owner": "PixelProwlers",
            "squad": (
                collab.get("preferred_partners", ["core"])[0]
                if collab.get("preferred_partners")
                else "core"
            ),
            "budget_tier": "medium",
            "default_sensitivity": "moyenne",
            "created_at": now,
            "updated_at": now,
            "manifest_hash_sha256": "",
        },
    }

    # Ajout d'instructions initiales si présentes (on les dépose dans governance/raison_d_etre + identity/description déjà)
    if data.get("instructions"):
        v21.setdefault("governance", {})
        v21["governance"]["raison_d_etre"] = (
            v21["governance"].get("raison_d_etre", "") + " | Guidelines: " + data["instructions"]
        )[:1200]

    return v21


def main():
    if len(sys.argv) != 3:
        print("Usage: python agents/tools/migrate_legacy_profiles.py <src_dir> <dst_dir>")
        sys.exit(2)
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()
    dst.mkdir(parents=True, exist_ok=True)

    count = 0
    for p in sorted(src.glob("*_agent.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                legacy = json.load(f)
            # si déjà au format v2.1, recopier tel quel
            if legacy.get("schema_version") == SCHEMA_VERSION:
                out = legacy
            else:
                out = migrate_one(legacy)
            # hash manifest
            # (optionnel ici: on le laisse vide, calculé côté utilitaires si nécessaire)
            out_path = dst / p.name
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            count += 1
        except Exception as e:
            print(f"❌ Erreur sur {p.name}: {e}")
            continue
    print(f"✅ Migration terminée. Fichiers générés: {count} → {dst}")
    sys.exit(0)


if __name__ == "__main__":
    main()
