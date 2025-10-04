# backend/ai_assistants/utils/agent_schema.py
# -*- coding: utf-8 -*-
"""
Schéma JSON canonique v2.1 pour les profils d'agents PixelProwlers + utilitaires.
Objectifs :
- Valider structure/contraintes (jsonschema Draft 2020-12)
- Empêcher les modifs sur champs immuables (ex: identity.slug, tools[].name)
- Calculer un hash stable du manifeste (manifest_hash_sha256)
- Faire respecter la politique budgétaire (≤ max_eur_per_day) et les caps token
- Fournir un CLI local pour valider/contrôler un profil

Sécurité (esprit "mode chacal") :
- additionalProperties=False au top-level pour éviter l'injection silencieuse
- Listes blanches et politiques explicites (models, network_allowlist, tools)
- Gates "preflight/go_live" pour imposer les check-points avant prod

Usage rapide (CLI) :
    python -m backend.ai_assistants.utils.agent_schema path/to/profile.json [path/to/old_profile.json]
Retour codes : 0 = OK ; 1 = erreurs schema ; 2 = erreurs immuables/budget ; 3 = autre erreur
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

try:
    from jsonschema import Draft202012Validator
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "jsonschema n'est pas installé. Fais : pip install jsonschema\n" f"Détail : {e}"
    )

SCHEMA_VERSION = "2.1.0"

# --------------------------------------------------------------------------------------
#  Schéma canonique v2.1 (équivalent Python du JSON Schema publié)
#  NB: Garder ce schéma comme source de vérité. Toute rupture -> bump major.
# --------------------------------------------------------------------------------------

AGENT_PROFILE_SCHEMA_V21: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pixelprowlers.io/schemas/agents_profile_v2_1.json",
    "title": "PixelProwlers Agent Profile (v2.1)",
    "type": "object",
    "required": [
        "schema_version",
        "profile_version",
        "identity",
        "model_policy",
        "security",
        "tools",
        "observability",
        "gates",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {
            "type": "string",
            "const": SCHEMA_VERSION,
            "description": "Version du schéma global.",
        },
        "profile_version": {
            "type": "string",
            "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$",
            "description": "Version sémantique du profil agent.",
        },
        "identity": {
            "type": "object",
            "required": ["name", "slug", "alias", "description"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "slug": {"type": "string", "pattern": r"^[a-z0-9-]+$"},
                "alias": {"type": "string"},
                "description": {"type": "string"},
            },
        },
        "governance": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "raison_d_etre",
                "missions",
                "raci",
                "decision_rights",
                "operating_modes",
                "default_mode",
            ],
            "properties": {
                "raison_d_etre": {"type": "string"},
                "missions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "circle_roles": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "lead": {"type": "string"},
                        "facilitator": {"type": "string"},
                        "secretary": {"type": "string"},
                        "risk_officer": {"type": "string"},
                    },
                },
                "raci": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["responsible", "accountable", "consulted", "informed"],
                    "properties": {
                        "responsible": {"type": "array", "items": {"type": "string"}},
                        "accountable": {"type": "array", "items": {"type": "string"}},
                        "consulted": {"type": "array", "items": {"type": "string"}},
                        "informed": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "decision_rights": {
                    "type": "object",
                    "additionalProperties": {"enum": ["autonomous", "with_approval", "forbidden"]},
                },
                "operating_modes": {
                    "type": "array",
                    "items": {"enum": ["advisory", "auto", "dry_run", "shadow"]},
                },
                "default_mode": {"enum": ["advisory", "auto", "dry_run", "shadow"]},
            },
        },
        "communication_style": {
            "type": "object",
            "additionalProperties": False,
            "required": ["tone", "sentence_length", "language_level"],
            "properties": {
                "tone": {"type": "string"},
                "sentence_length": {"enum": ["courte", "moyenne", "longue"]},
                "language_level": {"enum": ["débutant", "accessible-expert", "expert"]},
                "metaphor_usage": {"enum": ["faible", "modérée", "élevée"]},
                "emoji_usage": {"type": "boolean"},
                "disclaimers": {"type": "array", "items": {"type": "string"}},
            },
        },
        "model_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "provider_order",
                "allowed_models",
                "latency_slo_ms",
                "retries",
                "fallback",
                "rate_limits",
                "cache_policy",
                "budget_policy",
            ],
            "properties": {
                "provider_order": {
                    "type": "array",
                    "items": {"enum": ["local", "mid", "premium"]},
                    "minItems": 1,
                },
                "allowed_models": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "local": {"type": "array", "items": {"type": "string"}},
                        "mid": {"type": "array", "items": {"type": "string"}},
                        "premium": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "premium_unlock_required": {"type": "boolean", "default": True},
                "caps": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "daily_tokens_in": {"type": "integer", "minimum": 0},
                        "daily_tokens_out": {"type": "integer", "minimum": 0},
                    },
                },
                "latency_slo_ms": {"type": "integer", "minimum": 0},
                "retries": {"type": "integer", "minimum": 0, "maximum": 5},
                "fallback": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "on_timeout": {"enum": ["local", "mid", "premium", "none"]},
                        "on_policy_denied": {"enum": ["local", "mid", "premium", "none"]},
                    },
                },
                "rate_limits": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rpm": {"type": "integer", "minimum": 1},
                        "rph": {"type": "integer", "minimum": 1},
                    },
                },
                "cache_policy": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "ttl_seconds": {"type": "integer", "minimum": 0},
                    },
                },
                "budget_policy": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["max_eur_per_day", "hard_stop_on_exceed"],
                    "properties": {
                        "max_eur_per_day": {"type": "number", "minimum": 0},
                        "hard_stop_on_exceed": {"type": "boolean"},
                        "exhaust_local_first": {"type": "boolean", "default": True},
                    },
                },
            },
        },
        "security": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "data_minimization",
                "encryption_required",
                "anonymization_supported",
                "incident_alert_level",
                "forbidden_operations",
                "isolation_level",
            ],
            "properties": {
                "data_minimization": {"type": "boolean"},
                "encryption_required": {"type": "boolean"},
                "anonymization_supported": {"type": "boolean"},
                "incident_alert_level": {"enum": ["low", "medium", "high", "critical"]},
                "threat_model": {"type": "array", "items": {"type": "string"}},
                "pii_allowed": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "classes": {"type": "array", "items": {"type": "string"}},
                        "storage_rules": {"type": "string"},
                    },
                },
                "secrets_scope": {"type": "array", "items": {"type": "string"}},
                "network_allowlist": {"type": "array", "items": {"type": "string"}},
                "forbidden_operations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "isolation_level": {"enum": ["sandboxed", "privileged"]},
            },
        },
        "context": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sources": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "nextcloud_paths": {"type": "array", "items": {"type": "string"}},
                        "wiki_pages": {"type": "array", "items": {"type": "string"}},
                        "apis": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "retrieval": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rag_enabled": {"type": "boolean"},
                        "retriever": {"enum": ["embedding", "keyword", "hybrid"]},
                        "top_k": {"type": "integer", "minimum": 1},
                        "max_context_tokens": {"type": "integer", "minimum": 256},
                        "citation_required": {"type": "boolean"},
                        "freshness_max_days": {"type": "integer", "minimum": 0},
                    },
                },
                "privacy_filters": {"type": "array", "items": {"type": "string"}},
            },
        },
        "integrations": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "crm_systems": {"type": "array", "items": {"type": "string"}},
                "data_sync_frequency": {"enum": ["daily", "weekly", "monthly", "never"]},
                "webhooks_supported": {"type": "boolean"},
                "email_platforms": {"type": "array", "items": {"type": "string"}},
                "analytics": {"type": "array", "items": {"type": "string"}},
            },
        },
        "learning": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "model_update_mode": {"enum": ["manual_review", "auto", "off"]},
                "continuous_learning": {"type": "boolean"},
                "source_feedback": {"type": "array", "items": {"type": "string"}},
                "evaluation": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "offline_datasets": {"type": "array", "items": {"type": "string"}},
                        "rubrics": {"type": "array", "items": {"type": "string"}},
                        "schedule": {"type": "string"},
                        "quality_targets": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        "collaboration_protocol": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "preferred_partners": {"type": "array", "items": {"type": "string"}},
                "handoff_expectation": {"type": "string"},
                "collaboration_style": {"type": "string"},
                "acceptable_deviation_level": {"enum": ["low", "medium", "high"]},
            },
        },
        "compliance": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "gdpr": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "dpa_signed": {"type": "boolean"},
                        "data_retention_days": {"type": "integer", "minimum": 0},
                        "dsar_supported": {"type": "boolean"},
                    },
                },
                "consent_required": {"type": "boolean"},
                "logging_minimization": {"type": "boolean"},
            },
        },
        "observability": {
            "type": "object",
            "additionalProperties": False,
            "required": ["logs", "metrics", "alarms", "audit_trail"],
            "properties": {
                "logs": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fields": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "metrics": {"type": "array", "items": {"type": "string"}},
                "alarms": {"type": "array", "items": {"type": "string"}},
                "audit_trail": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "retention_days": {"type": "integer", "minimum": 0},
                    },
                },
            },
        },
        "gates": {
            "type": "object",
            "additionalProperties": False,
            "required": ["preflight", "go_live", "rollback_plan"],
            "properties": {
                "preflight": {"type": "array", "items": {"type": "string"}},
                "go_live": {"type": "array", "items": {"type": "string"}},
                "rollback_plan": {"type": "string"},
            },
        },
        "tools": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description", "parameters_schema", "returns"],
                "properties": {
                    "name": {"type": "string", "pattern": r"^[a-z0-9_\.\:-]+$"},
                    "description": {"type": "string"},
                    "parameters_schema": {"type": "object"},
                    "returns": {"type": "string"},
                    "scopes": {"type": "array", "items": {"type": "string"}},
                    "rate_limit": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"per_minute": {"type": "integer", "minimum": 1}},
                    },
                    "audit": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "redact_inputs": {"type": "boolean"},
                        },
                    },
                    "allowed_contexts": {
                        "type": "array",
                        "items": {"enum": ["dev", "test", "prod"]},
                    },
                },
            },
        },
        "immutable_fields": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["identity.name", "identity.slug", "tools[].name"],
        },
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "owner": {"type": "string"},
                "squad": {"type": "string"},
                "budget_tier": {"enum": ["ultra", "high", "medium", "low"]},
                "default_sensitivity": {"enum": ["basse", "moyenne", "haute"]},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "manifest_hash_sha256": {"type": "string"},
            },
        },
    },
}

# --------------------------------------------------------------------------------------
#  Fonctions utilitaires
# --------------------------------------------------------------------------------------


def get_agent_schema() -> Dict[str, Any]:
    """Retourne le schéma actif (v2.1)."""
    return AGENT_PROFILE_SCHEMA_V21


def validate_agent_profile(profile: Dict[str, Any]) -> List[str]:
    """
    Valide un profil contre le schéma v2.1.
    Retourne une liste d'erreurs lisibles ; vide si tout va bien.
    """
    schema = get_agent_schema()
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(profile), key=lambda e: e.path):
        path = "/".join(map(str, err.path)) or "(root)"
        errors.append(f"{path}: {err.message}")
    return errors


def _get_values_by_path(data: Any, path: str) -> List[Any]:
    """
    Récupère les valeurs d'un chemin 'a.b[].c' dans une structure dict/list.
    - '[]' indique de parcourir tous les éléments d'une liste.
    """
    parts = path.split(".")
    nodes = [data]
    for part in parts:
        new_nodes = []
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part
        for node in nodes:
            if isinstance(node, dict) and key in node:
                val = node[key]
                if is_array:
                    if isinstance(val, list):
                        new_nodes.extend(val)
                else:
                    new_nodes.append(val)
            elif isinstance(node, list):
                # Si le niveau est une liste et qu'on attend une clé, on itère
                for item in node:
                    if isinstance(item, dict) and key in item:
                        val = item[key]
                        if is_array:
                            if isinstance(val, list):
                                new_nodes.extend(val)
                        else:
                            new_nodes.append(val)
        nodes = new_nodes
    return nodes


def ensure_immutable_fields_unchanged(
    old: Optional[Dict[str, Any]],
    new: Dict[str, Any],
    immutable_paths: Optional[List[str]] = None,
) -> List[str]:
    """
    Vérifie que certains champs n'ont pas changé entre old et new.
    Supporte les chemins comme 'identity.slug' et 'tools[].name'.
    Retourne une liste d'erreurs ; vide = OK.

    Sécurité: empêche la "substitution d'identité" ou l'injection discrète d'outils.
    """
    if not old:
        return []  # première version: rien à comparer

    schema_default_immut = get_agent_schema()["properties"]["immutable_fields"]["default"]
    targets = immutable_paths or old.get("immutable_fields", schema_default_immut)

    errors: List[str] = []
    for path in targets:
        old_vals = _get_values_by_path(old, path)
        new_vals = _get_values_by_path(new, path)
        if old_vals != new_vals:
            errors.append(f"Champ immuable modifié: '{path}' (old={old_vals} vs new={new_vals})")
    return errors


def compute_manifest_hash(profile: Dict[str, Any]) -> str:
    """
    Calcule un hash SHA256 stable du profil, en excluant metadata.manifest_hash_sha256.
    - Sérialisation JSON triée (sort_keys=True), sans espace inutile.
    """
    data = deepcopy(profile)
    meta = data.get("metadata", {})
    if "manifest_hash_sha256" in meta:
        # on n'inclut pas l'ancien hash dans le calcul
        meta.pop("manifest_hash_sha256", None)
        data["metadata"] = meta
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enforce_budget_and_caps(
    profile: Dict[str, Any],
    spent_today_eur: float,
    tokens_in_today: int = 0,
    tokens_out_today: int = 0,
) -> List[str]:
    """
    Vérifie que la politique budgétaire et les caps token sont respectés.
    Retourne des erreurs si dépassement.
    """
    errs: List[str] = []
    mp = profile.get("model_policy", {})
    budget = mp.get("budget_policy", {})
    caps = mp.get("caps", {})

    max_eur = float(budget.get("max_eur_per_day", 0.0))
    hard_stop = bool(budget.get("hard_stop_on_exceed", True))

    if spent_today_eur > max_eur and hard_stop:
        errs.append(
            f"Budget journalier dépassé: {spent_today_eur:.2f}€ > {max_eur:.2f}€ (hard stop)."
        )

    d_in = int(caps.get("daily_tokens_in", 0))
    d_out = int(caps.get("daily_tokens_out", 0))
    if d_in and tokens_in_today > d_in:
        errs.append(f"Cap tokens_in dépassé: {tokens_in_today} > {d_in}")
    if d_out and tokens_out_today > d_out:
        errs.append(f"Cap tokens_out dépassé: {tokens_out_today} > {d_out}")

    return errs


# --------------------------------------------------------------------------------------
#  CLI de validation rapide
# --------------------------------------------------------------------------------------


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main_cli(argv: List[str]) -> int:
    if not (2 <= len(argv) <= 3):
        print(
            "Usage: python -m backend.ai_assistants.utils.agent_schema PROFILE.json [OLD_PROFILE.json]"
        )
        return 3

    profile = _load_json(argv[1])
    old = _load_json(argv[2]) if len(argv) == 3 else None

    # 1) Validation schéma
    schema_errors = validate_agent_profile(profile)
    if schema_errors:
        print("❌ Erreurs de schéma:")
        for e in schema_errors:
            print("  -", e)
        return 1

    # 2) Immuables
    immu_errors = ensure_immutable_fields_unchanged(old, profile) if old else []
    if immu_errors:
        print("❌ Champs immuables modifiés:")
        for e in immu_errors:
            print("  -", e)
        return 2

    # 3) Hash manifeste
    manifest_hash = compute_manifest_hash(profile)
    print("✅ Schéma OK")
    print("✅ Immuables OK (ou première version)")
    print("🔐 manifest_hash_sha256 =", manifest_hash)

    # 4) Exemple de contrôle budget (valeurs factices ici)
    budget_errs = enforce_budget_and_caps(
        profile,
        spent_today_eur=0.0,  # à renseigner depuis vos compteurs runtime
        tokens_in_today=0,
        tokens_out_today=0,
    )
    if budget_errs:
        print("⚠️  Budget/caps à risque:")
        for e in budget_errs:
            print("  -", e)
        # on ne met pas code erreur ici: c'est un avertissement hors runtime

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main_cli(sys.argv))
