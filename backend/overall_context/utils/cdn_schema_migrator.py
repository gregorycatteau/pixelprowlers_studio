#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cdn_schema_migrator.py
Migration de blocs ZoneBlock vers la version de schéma 1.1.0.

Usage:
  python cdn_schema_migrator.py cdn_zones/Z3.json --in-place
  python cdn_schema_migrator.py cdn_zones/ --in-place

Sécurité:
- Backup local systématique (non chiffré ici; le chiffrage sera géré par backup_encryptor.py).
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List

ALLOWED_VISIBILITY_V11 = [
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


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_zone_files(target: str) -> List[str]:
    if os.path.isdir(target):
        return sorted([os.path.join(target, f) for f in os.listdir(target) if f.endswith(".json")])
    if os.path.isfile(target) and target.endswith(".json"):
        return [target]
    return []


def ensure_path(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def backup_file(src_path: str, backup_root: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dst_dir = os.path.join(backup_root, stamp)
    ensure_path(dst_dir)
    base = os.path.basename(src_path)
    dst = os.path.join(dst_dir, base + ".bak.json")
    shutil.copy2(src_path, dst)
    return dst


def migrate_zone(zone: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applique une migration soft v1.0 -> v1.1 :
    - Ajoute 'schema_version': '1.1.0'
    - access_policy: ajoute project_specific_overrides (False par défaut si absent)
    - visibility_levels: normalise vers la liste v1.1 si nécessaire
    - versioning_policy: force 'contextual' + ajoute 'retention_rules' par défaut si absent
    - metrics_template: ajoute clés critiques si manquantes
    """
    # Schema version
    zone["schema_version"] = "1.1.0"

    # Access policy
    ap = zone.setdefault("access_policy", {})
    ap.setdefault("project_specific_overrides", True)
    vis = ap.get("visibility_levels")
    if not isinstance(vis, list) or not vis:
        ap["visibility_levels"] = ALLOWED_VISIBILITY_V11
    else:
        # Union sécurisée + ordre canonique
        s = {v for v in vis if v in ALLOWED_VISIBILITY_V11}
        for v in ALLOWED_VISIBILITY_V11:
            if v not in s:
                # On n'impose pas tout, on respecte la sélection existante
                pass
        # Garder l'existant, mais enlever les niveaux inconnus
        ap["visibility_levels"] = [v for v in vis if v in ALLOWED_VISIBILITY_V11]

    ap.setdefault("auth_required", True)
    ap.setdefault("queryable_by_default", False)
    ap.setdefault("default_sensitivity", ap.get("default_sensitivity", "internal"))

    # Versioning / Rétention
    vp = zone.setdefault("versioning_policy", {})
    vp["retention_policy"] = "contextual"
    rr = vp.setdefault("retention_rules", {})
    rr.setdefault("prod_feature", "infinite")
    rr.setdefault("internal_doc", "6_months")
    rr.setdefault("sensitive_logs", "30_days")
    rr.setdefault("pentest_files", "suppress_retention")
    vp.setdefault("strategy", "immutable")
    vp.setdefault("require_changelog", True)

    # Metrics post-incident
    mt = zone.setdefault("metrics_template", {})
    mt.setdefault("track_usage", True)
    mt.setdefault("track_last_accessed", True)
    mt.setdefault("track_modifications", True)
    mt.setdefault("log_extraction_attempts", True)
    mt.setdefault("alert_on_unauthorized_access", True)
    mt.setdefault(
        "anomaly_score",
        {
            "enabled": True,
            "weighting": {
                "access_frequency": 0.2,
                "deviation_from_role": 0.4,
                "context_leak_risk": 0.4,
            },
        },
    )
    mt.setdefault(
        "forensic_hooks",
        {
            "on_delete": "dump_to_vault",
            "on_access_by_redflagged_role": "mirror_to_monitoring",
            "on_contextual_conflict": "trigger_alert_chain",
        },
    )

    return zone


def main():
    parser = argparse.ArgumentParser(
        description="Migre des blocs ZoneBlock vers le schéma 1.1.0 (avec backup)."
    )
    parser.add_argument("target", help="Fichier Zx.json ou dossier cdn_zones/")
    parser.add_argument(
        "--in-place", action="store_true", help="Écrase le fichier source après migration."
    )
    parser.add_argument(
        "--backup-root",
        default="./.context_backups",
        help="Répertoire de backups (sera créé si absent).",
    )
    args = parser.parse_args()

    files = list_zone_files(args.target)
    if not files:
        print("Aucun fichier .json trouvé.")
        return 2

    ensure_path(args.backup_root)

    migrated = 0
    for path in files:
        try:
            original = load_json(path)
            # Sauvegarde avant migration
            bkp = backup_file(path, args.backup_root)
            new = migrate_zone(original)
            if args.__dict__.get("in_place"):
                save_json(path, new)
                print(f"✔ Migré: {path}  (backup: {bkp})")
            else:
                out = path.replace(".json", ".migrated.json")
                save_json(out, new)
                print(f"✔ Migré: {path}  → {out}  (backup: {bkp})")
            migrated += 1
        except Exception as e:
            print(f"❌ Échec migration {path}: {e}")

    print(f"\nRésumé: {migrated}/{len(files)} fichiers migrés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
