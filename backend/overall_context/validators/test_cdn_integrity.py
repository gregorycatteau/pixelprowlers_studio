#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_cdn_integrity.py (v2 – locked)
Audit global: cohérence zones ↔ schémas ↔ registre, avec traçage d'origine
des bindings inconnus et enforcement strict.

Bloque si:
  - Au moins une zone invalide
  - Bindings (squads/agents) référencent des entrées inconnues (avec trace)
  - best_practice sans provenance vérifiée/reproduite

Usage:
  python test_cdn_integrity.py --zones ./cdn_zones/data \
    --schema ./cdn_zones/data/cdn_schema_v1.2.json \
    --op-schema ./cdn_zones/data/cdn_schema_operational_v1.1.json \
    --registry ./cdn_zones/data/cdn_registry.json \
    --squads-registry ./squads_registry.json \
    --agents-registry ./agents_registry.json \
    --mode auto --pretty
"""

import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

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


def load_json(p: str) -> Dict[str, Any]:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_zone_files(zones_dir: str) -> List[str]:
    return sorted(
        [os.path.join(zones_dir, f) for f in os.listdir(zones_dir) if f.endswith(".json")]
    )


def detect_mode(zone: Dict[str, Any]) -> str:
    if any(k in zone for k in ("zone_id", "zone_code", "visibility")):
        return "operational"
    return "conceptual"


def validate_conceptual(
    zone: Dict[str, Any], schema: Dict[str, Any]
) -> Tuple[bool, List[str], List[str]]:
    errors, warnings = [], []
    required = [
        "id",
        "code",
        "label",
        "description",
        "intent_scope",
        "access_policy",
        "structure_schema",
        "recommended_tags",
        "versioning_policy",
        "security_controls",
        "metrics_template",
        "schema_version",
    ]
    for k in required:
        if k not in zone:
            errors.append(f"Champ manquant: {k}")

    ap = zone.get("access_policy", {})
    if "visibility_levels" not in ap or not isinstance(ap["visibility_levels"], list):
        errors.append("access_policy.visibility_levels absent/incorrect.")
    else:
        bad = [v for v in ap["visibility_levels"] if v not in ALLOWED_VISIBILITY_LEVELS]
        if bad:
            errors.append(f"Niveaux de visibilité inconnus: {bad}")

    rc = zone.get("rag_config", {})
    if isinstance(rc, dict):
        bad = [v for v in rc.get("index_visibility", []) if v not in ALLOWED_VISIBILITY_LEVELS]
        if bad:
            errors.append(f"rag_config.index_visibility non autorisée: {bad}")

    # best_practice provenance (bloquant)
    if zone.get("zone_type") == "best_practice":
        prov = zone.get("provenance", {})
        if not (prov.get("verified") or prov.get("reproduced_in_lab")):
            errors.append("best_practice sans provenance vérifiée ni reproduction labo (bloquant).")

    # deception (bloquant si incohérent)
    dec = zone.get("deception_controls", {})
    if isinstance(dec, dict) and dec.get("enabled") and not dec.get("honey_rank", 0) > 0:
        errors.append("deception_controls.enabled=true mais honey_rank<=0.")

    # version (souple)
    sv = str(zone.get("schema_version"))
    expected = str(schema.get("schema_version", "1.2.0"))
    if sv != expected:
        warnings.append(f"schema_version={sv}, attendu={expected} (migration possible).")

    return (len(errors) == 0), errors, warnings


def validate_operational(
    zone: Dict[str, Any], op_schema: Dict[str, Any]
) -> Tuple[bool, List[str], List[str]]:
    errors, warnings = [], []
    for k in op_schema.get("required_fields", []):
        if k not in zone:
            errors.append(f"Champ manquant: {k}")

    vis = zone.get("visibility")
    if vis and vis not in ALLOWED_VISIBILITY_LEVELS:
        errors.append(f"visibility '{vis}' non autorisée.")

    rc = zone.get("rag_config", {})
    if isinstance(rc, dict) and rc.get("citation_required"):
        content = zone.get("content", {})
        if not (content.get("citations") or content.get("sources")):
            errors.append("citation_required=true sans citations/sources dans content.")
        bad = [v for v in rc.get("index_visibility", []) if v not in ALLOWED_VISIBILITY_LEVELS]
        if bad:
            errors.append(f"rag_config.index_visibility non autorisée: {bad}")

    dec = zone.get("deception_controls", {})
    if isinstance(dec, dict) and dec.get("enabled") and not dec.get("honey_rank", 0) > 0:
        errors.append("deception_controls.enabled=true mais honey_rank<=0.")

    sv = str(zone.get("schema_version", "1.1"))
    expected = str(op_schema.get("schema_version", "1.1"))
    if sv != expected:
        warnings.append(f"schema_version={sv}, attendu={expected} (ok si migration en cours).")

    return (len(errors) == 0), errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Audit d'intégrité du CDN (zones/schémas/registre) – strict."
    )
    parser.add_argument("--zones", required=True, help="Répertoire cdn_zones/data/")
    parser.add_argument("--schema", required=True, help="Chemin schéma conceptuel v1.2")
    parser.add_argument("--op-schema", required=True, help="Chemin schéma opérationnel v1.1")
    parser.add_argument("--registry", required=True, help="Chemin cdn_registry.json")
    parser.add_argument(
        "--mode",
        choices=["auto", "conceptual", "operational"],
        default="auto",
        help="Mode d'analyse (auto par défaut).",
    )
    parser.add_argument("--squads-registry", required=False, help="Chemin squads_registry.json")
    parser.add_argument("--agents-registry", required=False, help="Chemin agents_registry.json")
    parser.add_argument("--pretty", action="store_true", help="Affichage humain.")
    args = parser.parse_args()

    schema = load_json(args.schema)
    op_schema = load_json(args.op_schema)
    registry = load_json(args.registry)
    files = list_zone_files(args.zones)

    report: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "zones_dir": args.zones,
        "checked": len(files),
        "results": [],
        "registry_sync": {"missing_in_registry": [], "ghost_in_registry": []},
        "bindings_check": {"unknown_squads": {}, "unknown_agents": {}},
        "bindings_trace": {
            "squads": {},
            "agents": {},
        },  # reverse map: unknown -> [ {zone_id,file,json_pointer} ]
    }

    # Registres connus (pour lock)
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

    ids_seen: Set[str] = set()
    for fp in files:
        try:
            zone = load_json(fp)
            mode = args.mode if args.mode != "auto" else detect_mode(zone)

            if mode == "operational":
                ok, errs, warns = validate_operational(zone, op_schema)
                zid = zone.get("zone_id") or os.path.basename(fp)
                reg_key = "zone_id"
            else:
                ok, errs, warns = validate_conceptual(zone, schema)
                zid = zone.get("id") or os.path.basename(fp)
                reg_key = "id"

                # Enforce bindings strict + traçage
                bindings = zone.get("bindings", {})
                if isinstance(bindings, dict):
                    # squads
                    for i, s in enumerate(bindings.get("squad_ids") or []):
                        if known_squads and s not in known_squads:
                            errs.append(f"Binding squad inconnu: {s}")
                            report["bindings_check"]["unknown_squads"].setdefault(zid, []).append(s)
                            report["bindings_trace"]["squads"].setdefault(s, []).append(
                                {
                                    "zone_id": zid,
                                    "file": fp,
                                    "json_pointer": f"/bindings/squad_ids/{i}",
                                }
                            )
                    # agents
                    for j, a in enumerate(bindings.get("agent_ids") or []):
                        if known_agents and a not in known_agents:
                            errs.append(f"Binding agent inconnu: {a}")
                            report["bindings_check"]["unknown_agents"].setdefault(zid, []).append(a)
                            report["bindings_trace"]["agents"].setdefault(a, []).append(
                                {
                                    "zone_id": zid,
                                    "file": fp,
                                    "json_pointer": f"/bindings/agent_ids/{j}",
                                }
                            )

            ids_seen.add(zid)

            report["results"].append(
                {
                    "file": fp,
                    "zone_id": zid,
                    "mode": mode,
                    "ok": ok,
                    "errors": errs,
                    "warnings": warns,
                    "registry_key": reg_key,
                }
            )
        except Exception as e:
            report["results"].append(
                {
                    "file": fp,
                    "zone_id": None,
                    "mode": "unknown",
                    "ok": False,
                    "errors": [f"Exception: {repr(e)}"],
                    "warnings": [],
                }
            )

    # Registry sync
    reg_ids = {e.get("id") for e in registry.get("entries", [])}
    report["registry_sync"]["missing_in_registry"] = sorted(list(ids_seen - reg_ids))
    report["registry_sync"]["ghost_in_registry"] = sorted(list(reg_ids - ids_seen))

    if args.pretty:
        print(f"\n=== CDN INTEGRITY REPORT @ {report['timestamp']} ===")
        for r in report["results"]:
            status = "OK " if r["ok"] else "ERR"
            print(f"[{status}] ({r['mode']}) {r['zone_id'] or '??'} :: {r['file']}")
            for e in r["errors"]:
                print(f"   - ERR: {e}")
            for w in r["warnings"]:
                print(f"   - WRN: {w}")
        print("\n--- Registry sync ---")
        print("  Missing in registry:", report["registry_sync"]["missing_in_registry"])
        print("  Ghost in registry  :", report["registry_sync"]["ghost_in_registry"])
        if report["bindings_trace"]["squads"] or report["bindings_trace"]["agents"]:
            print("\n--- Bindings TRACE (origine des références inconnues) ---")
            if report["bindings_trace"]["squads"]:
                print("  Squads inconnues:")
                for k, refs in report["bindings_trace"]["squads"].items():
                    print(f"   - {k}:")
                    for ref in refs:
                        print(
                            f"       · zone={ref['zone_id']} file={ref['file']} path={ref['json_pointer']}"
                        )
            if report["bindings_trace"]["agents"]:
                print("  Agents inconnus:")
                for k, refs in report["bindings_trace"]["agents"].items():
                    print(f"   - {k}:")
                    for ref in refs:
                        print(
                            f"       · zone={ref['zone_id']} file={ref['file']} path={ref['json_pointer']}"
                        )
        print("")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # Code retour: fail si au moins une zone invalide OU si bindings inconnus détectés (registries fournis)
    any_invalid = not all(r["ok"] for r in report["results"])
    unknown_bindings = bool(
        report["bindings_check"]["unknown_squads"] or report["bindings_check"]["unknown_agents"]
    )
    exit_code = 1 if (any_invalid or unknown_bindings) else 0
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
