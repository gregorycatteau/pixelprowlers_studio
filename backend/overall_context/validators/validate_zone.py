#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_zone.py (v2 – locked)
Valide des blocs de zone CDN PixelProwlers (conceptuel v1.2 & opérationnel v1.1).

• Bloque si:
  - zone_type == "best_practice" sans provenance.verified ni reproduced_in_lab
  - rag_config.citation_required == true sans citations/sources
  - deception_controls.enabled == true avec honey_rank <= 0
  - rag_config.index_visibility contient des valeurs hors allowlist

• Optionnel: vérifie les bindings (squads/agents) contre des registres fournis.
  --squads-registry ./squads_registry.json
  --agents-registry ./agents_registry.json
  --enforce-bindings (par défaut True si registres fournis)

Usage:
  python validate_zone.py cdn_zones/data/Z3.json --pretty
  python validate_zone.py cdn_zones/data/ --strict --pretty
  python validate_zone.py cdn_zones/data/ --mode operational
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

# === Constantes & chemins par défaut ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

DEFAULT_SCHEMA_CONCEPTUAL = os.path.join(DATA_DIR, "cdn_schema_v1.2.json")
DEFAULT_SCHEMA_OPERATIONAL = os.path.join(DATA_DIR, "cdn_schema_operational_v1.1.json")

ALLOWED_VISIBILITY_LEVELS = [
    "public",
    "clients",
    "project_member",
    "external_admin",
    "internal_admin",
    "ngner_only",
    "striker_only",
    "redteam_only",
    "hidden",
]


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_zone_files(target: str) -> List[str]:
    if os.path.isdir(target):
        return sorted([os.path.join(target, f) for f in os.listdir(target) if f.endswith(".json")])
    if os.path.isfile(target) and target.endswith(".json"):
        return [target]
    return []


def detect_mode(zone_doc: Dict[str, Any]) -> str:
    if any(k in zone_doc for k in ("zone_id", "zone_code", "visibility")):
        return "operational"
    return "conceptual"


# ---------- Conceptuel (v1.2) ----------
def required_keys_conceptual(schema: Dict[str, Any]) -> List[str]:
    struct = schema.get("structure", {})
    keys = list(struct.keys())
    keys.append("schema_version")
    return keys


def validate_types_conceptual(zone: Dict[str, Any]) -> List[str]:
    errors = []
    # Champs fréquent/conseillés
    if "id" in zone and not isinstance(zone.get("id"), str):
        errors.append("Le champ 'id' doit être une chaîne.")
    if "label" in zone and not isinstance(zone.get("label"), str):
        errors.append("Le champ 'label' doit être une chaîne.")
    if "intent_scope" in zone and not isinstance(zone.get("intent_scope"), list):
        errors.append("Le champ 'intent_scope' doit être une liste.")
    for k in (
        "access_policy",
        "structure_schema",
        "versioning_policy",
        "security_controls",
        "metrics_template",
    ):
        if k in zone and not isinstance(zone.get(k), dict):
            errors.append(f"Le champ '{k}' doit être un objet.")
    for k in ("recommended_tags",):
        if k in zone and not isinstance(zone.get(k), list):
            errors.append(f"Le champ '{k}' doit être une liste.")
    # v1.2
    for k in (
        "rag_config",
        "deception_controls",
        "bindings",
        "interfaces",
        "model_policies",
        "slo_kpis",
    ):
        if k in zone and not isinstance(zone.get(k), dict):
            errors.append(f"Le champ '{k}' doit être un objet.")
    return errors


def validate_access_policy(zone: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    ap = zone.get("access_policy", {})
    if not isinstance(ap, dict):
        return (["'access_policy' doit être un objet."], warnings)
    vis_levels = ap.get("visibility_levels", [])
    if not isinstance(vis_levels, list):
        errors.append("'access_policy.visibility_levels' doit être une liste.")
        return errors, warnings
    unknown = [v for v in vis_levels if v not in ALLOWED_VISIBILITY_LEVELS]
    if unknown:
        errors.append(f"Niveaux de visibilité inconnus: {unknown}")
    if "auth_required" not in ap:
        warnings.append("Champ 'access_policy.auth_required' manquant (recommandé).")
    if "queryable_by_default" not in ap:
        warnings.append("Champ 'access_policy.queryable_by_default' manquant (recommandé).")
    if "default_sensitivity" not in ap:
        warnings.append("Champ 'access_policy.default_sensitivity' manquant (recommandé).")
    return errors, warnings


def validate_versioning_policy(zone: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    vp = zone.get("versioning_policy", {})
    if not isinstance(vp, dict):
        return (["'versioning_policy' doit être un objet."], warnings)
    if vp.get("retention_policy") == "contextual":
        rr = vp.get("retention_rules", {})
        for k in ["prod_feature", "internal_doc", "sensitive_logs", "pentest_files"]:
            if k not in rr:
                warnings.append(f"Règle de rétention '{k}' manquante dans 'retention_rules'.")
    else:
        warnings.append("Recommandé: 'retention_policy' = 'contextual'.")
    return errors, warnings


def validate_rag_config_conceptual(zone: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    rc = zone.get("rag_config", {})
    if not rc:
        return errors, warnings
    idx_vis = rc.get("index_visibility", [])
    bad = [v for v in idx_vis if v not in ALLOWED_VISIBILITY_LEVELS]
    if bad:
        errors.append(f"rag_config.index_visibility contient des valeurs non autorisées: {bad}")
    chunk = rc.get("chunking", {})
    if chunk and any(
        not isinstance(chunk.get(k), int) for k in ("max_chars", "overlap") if k in chunk
    ):
        warnings.append("rag_config.chunking.max_chars/overlap devraient être des entiers.")
    return errors, warnings


def validate_deception_conceptual(zone: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    dec = zone.get("deception_controls", {})
    if isinstance(dec, dict) and dec.get("enabled") and not dec.get("honey_rank", 0) > 0:
        errors.append("deception_controls.enabled=true mais honey_rank<=0.")
    return errors, warnings


def validate_provenance_best_practice(zone: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    if zone.get("zone_type") == "best_practice":
        prov = zone.get("provenance", {})
        verified = bool(prov.get("verified"))
        reproduced = bool(prov.get("reproduced_in_lab"))
        if not (verified or reproduced):
            errors.append("best_practice sans provenance vérifiée ni reproduction labo (bloquant).")
    return errors, warnings


def validate_bindings(
    zone: Dict[str, Any], known_squads: Set[str], known_agents: Set[str], enforce: bool
) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    bindings = zone.get("bindings", {})
    if not isinstance(bindings, dict):
        return errors, warnings
    unk_sq = (
        [s for s in (bindings.get("squad_ids") or []) if s not in known_squads]
        if known_squads
        else []
    )
    unk_ag = (
        [a for a in (bindings.get("agent_ids") or []) if a not in known_agents]
        if known_agents
        else []
    )
    if enforce and (unk_sq or unk_ag):
        if unk_sq:
            errors.append(f"Bindings squads inconnus: {unk_sq}")
        if unk_ag:
            errors.append(f"Bindings agents inconnus: {unk_ag}")
    elif unk_sq or unk_ag:
        if unk_sq:
            warnings.append(f"Bindings squads inconnus (non bloquant sans registre): {unk_sq}")
        if unk_ag:
            warnings.append(f"Bindings agents inconnus (non bloquant sans registre): {unk_ag}")
    return errors, warnings


def validate_conceptual(
    zone: Dict[str, Any],
    schema: Dict[str, Any],
    strict: bool,
    known_squads: Set[str],
    known_agents: Set[str],
    enforce_bindings: bool,
) -> Tuple[bool, List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    req = required_keys_conceptual(schema)
    for k in req:
        if k not in zone:
            (errors if strict else warnings).append(f"Champ manquant: '{k}'")

    errors.extend(validate_types_conceptual(zone))

    sv = str(zone.get("schema_version"))
    expected = str(schema.get("schema_version", "1.2.0"))
    if not sv:
        (errors if strict else warnings).append(
            f"Absence de 'schema_version'. Attendu: '{expected}'."
        )
    elif sv != expected:
        (errors if strict else warnings).append(f"schema_version='{sv}' différent de '{expected}'.")

    e, w = validate_access_policy(zone)
    errors.extend(e)
    warnings.extend(w)
    e, w = validate_versioning_policy(zone)
    errors.extend(e)
    warnings.extend(w)
    e, w = validate_rag_config_conceptual(zone)
    errors.extend(e)
    warnings.extend(w)
    e, w = validate_deception_conceptual(zone)
    errors.extend(e)
    warnings.extend(w)
    e, w = validate_provenance_best_practice(zone)
    errors.extend(e)
    warnings.extend(w)
    e, w = validate_bindings(zone, known_squads, known_agents, enforce_bindings)
    errors.extend(e)
    warnings.extend(w)

    ok = len(errors) == 0
    return ok, errors, warnings


# ---------- Opérationnel (v1.1) ----------
def validate_operational(
    zone: Dict[str, Any], op_schema: Dict[str, Any], strict: bool
) -> Tuple[bool, List[str], List[str]]:
    errors, warnings = [], []
    for k in op_schema.get("required_fields", []):
        if k not in zone:
            (errors if strict else warnings).append(f"Champ manquant: '{k}'")

    ft = op_schema.get("field_types", {})
    for k, t in ft.items():
        if k in zone:
            if t == "str" and not isinstance(zone.get(k), str):
                errors.append(f"Le champ '{k}' doit être une chaîne.")
            if t == "list" and not isinstance(zone.get(k), list):
                errors.append(f"Le champ '{k}' doit être une liste.")
            if t == "dict" and not isinstance(zone.get(k), dict):
                errors.append(f"Le champ '{k}' doit être un objet.")

    vis = zone.get("visibility")
    if vis and vis not in ALLOWED_VISIBILITY_LEVELS:
        errors.append(f"visibility '{vis}' non autorisée.")

    rc = zone.get("rag_config", {})
    if isinstance(rc, dict) and rc.get("citation_required"):
        content = zone.get("content", {})
        if not (content.get("citations") or content.get("sources")):
            errors.append("citation_required=true sans 'citations'/'sources' dans 'content'.")
        bad = [v for v in rc.get("index_visibility", []) if v not in ALLOWED_VISIBILITY_LEVELS]
        if bad:
            errors.append(f"rag_config.index_visibility non autorisée: {bad}")

    dec = zone.get("deception_controls", {})
    if isinstance(dec, dict) and dec.get("enabled") and not dec.get("honey_rank", 0) > 0:
        errors.append("deception_controls.enabled=true mais honey_rank<=0.")

    return (len(errors) == 0), errors, warnings


# ---------- Orchestrateur ----------
def main():
    parser = argparse.ArgumentParser(
        description="Valide des blocs de zone (conceptuels v1.2 ou opérationnels v1.1)."
    )
    parser.add_argument("target", help="Fichier .json ou dossier contenant des Z*.json")
    parser.add_argument(
        "--mode",
        choices=["auto", "conceptual", "operational"],
        default="auto",
        help="Type de validation (auto par défaut).",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA_CONCEPTUAL,
        help="Chemin vers cdn_schema_v1.2.json (conceptuel).",
    )
    parser.add_argument(
        "--op-schema",
        default=DEFAULT_SCHEMA_OPERATIONAL,
        help="Chemin vers cdn_schema_operational_v1.1.json (opérationnel).",
    )
    parser.add_argument("--squads-registry", help="Chemin squads_registry.json (optionnel)")
    parser.add_argument("--agents-registry", help="Chemin agents_registry.json (optionnel)")
    parser.add_argument(
        "--enforce-bindings",
        action="store_true",
        help="Échec si bindings inconnus (nécessite registres).",
    )
    parser.add_argument(
        "--strict", action="store_true", help="Échec si des champs manquent (sinon warnings)."
    )
    parser.add_argument("--pretty", action="store_true", help="Affichage lisible pour humains.")
    args = parser.parse_args()

    # Schémas
    try:
        schema_concept = load_json(os.path.abspath(args.schema))
    except Exception as e:
        print(
            json.dumps({"ok": False, "error": f"Impossible de charger le schéma conceptuel: {e}"})
        )
        sys.exit(2)
    try:
        schema_oper = load_json(os.path.abspath(args.op_schema))
    except Exception as e:
        print(
            json.dumps({"ok": False, "error": f"Impossible de charger le schéma opérationnel: {e}"})
        )
        sys.exit(2)

    # Registres bindings
    known_squads: Set[str] = set()
    known_agents: Set[str] = set()
    if args.squads_registry and os.path.exists(args.squads_registry):
        try:
            for e in load_json(args.squads_registry).get("entries", []):
                name = e.get("name") or e.get("id")
                if name:
                    known_squads.add(name)
        except Exception:
            pass
    if args.agents_registry and os.path.exists(args.agents_registry):
        try:
            for e in load_json(args.agents_registry).get("entries", []):
                name = e.get("name") or e.get("id")
                if name:
                    known_agents.add(name)
        except Exception:
            pass

    files = find_zone_files(args.target)
    if not files:
        print(json.dumps({"ok": False, "error": "Aucun fichier .json trouvé à valider."}))
        sys.exit(2)

    global_ok = True
    results = []

    for path in files:
        try:
            zone = load_json(path)
            mode = args.mode if args.mode != "auto" else detect_mode(zone)

            if mode == "operational":
                ok, errors, warnings = validate_operational(zone, schema_oper, args.strict)
                expected_sv = str(schema_oper.get("schema_version", "1.1"))
                sv = str(zone.get("schema_version", expected_sv))
                if sv and sv != expected_sv:
                    (errors if args.strict else warnings).append(
                        f"schema_version(opérationnel)='{sv}' différent de '{expected_sv}'."
                    )
            else:
                ok, errors, warnings = validate_conceptual(
                    zone,
                    schema_concept,
                    args.strict,
                    known_squads,
                    known_agents,
                    args.enforce_bindings and (known_squads or known_agents),
                )
                expected_sv = str(schema_concept.get("schema_version", "1.2.0"))
                sv = str(zone.get("schema_version", expected_sv))
                if sv and sv != expected_sv:
                    (errors if args.strict else warnings).append(
                        f"schema_version(conceptuel)='{sv}' différent de '{expected_sv}'."
                    )

            file_hash = sha256_file(path)
            results.append(
                {
                    "file": path,
                    "sha256": file_hash,
                    "mode": mode,
                    "ok": ok,
                    "errors": errors,
                    "warnings": warnings,
                    "checked_at": datetime.utcnow().isoformat() + "Z",
                }
            )
            if not ok:
                global_ok = False
        except Exception as e:
            results.append(
                {
                    "file": path,
                    "mode": "unknown",
                    "ok": False,
                    "errors": [f"Exception: {repr(e)}"],
                    "warnings": [],
                    "checked_at": datetime.utcnow().isoformat() + "Z",
                }
            )
            global_ok = False

    if args.pretty:
        for r in results:
            status = "✅ OK" if r["ok"] else "❌ FAIL"
            print(f"\n{status} [{r['mode']}] {r['file']}  (sha256={r['sha256']})")
            if r["errors"]:
                print("  Erreurs:")
                for e in r["errors"]:
                    print(f"   - {e}")
            if r["warnings"]:
                print("  Warnings:")
                for w in r["warnings"]:
                    print(f"   - {w}")
        print("")
    else:
        print(json.dumps({"ok": global_ok, "results": results}, ensure_ascii=False))

    sys.exit(0 if global_ok else 1)


if __name__ == "__main__":
    main()
