import json
import os
import re
from datetime import datetime
from pathlib import Path

# === CONFIGURATION ===
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = PROJECT_ROOT / ".context_backups"
MAX_BACKUPS_PER_ZONE = 3  # 🔁 Modifiable selon la stratégie

# === RÉGEX DE RECONNAISSANCE DES FICHIERS DE ZONE ===
BACKUP_PATTERN = re.compile(r"(?P<zone>Z\d+)__(?P<timestamp>\d{8}-\d{6})\.bin")


def list_backups():
    """
    Regroupe les backups par zone et trie par date décroissante.
    """
    backups_by_zone = {}

    for file in BACKUP_DIR.glob("*.bin"):
        match = BACKUP_PATTERN.match(file.name)
        if not match:
            continue

        zone = match.group("zone")
        timestamp = match.group("timestamp")

        try:
            dt = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
        except ValueError:
            continue

        backups_by_zone.setdefault(zone, []).append((dt, file))

    # Tri décroissant par date
    for zone in backups_by_zone:
        backups_by_zone[zone].sort(reverse=True)

    return backups_by_zone


def purge_old_backups():
    """
    Supprime les sauvegardes excédentaires par zone, ainsi que leurs manifests.
    """
    backups = list_backups()
    deleted = []

    for zone, versions in backups.items():
        if len(versions) <= MAX_BACKUPS_PER_ZONE:
            continue

        to_delete = versions[MAX_BACKUPS_PER_ZONE:]
        for dt, bin_file in to_delete:
            manifest_file = BACKUP_DIR / (bin_file.stem + ".json")
            try:
                bin_file.unlink()
                if manifest_file.exists():
                    manifest_file.unlink()
                deleted.append((zone, bin_file.name))
            except Exception as e:
                print(f"❌ Erreur suppression {bin_file.name}: {e}")

    return deleted


if __name__ == "__main__":
    if not BACKUP_DIR.exists():
        print("❌ Dossier de sauvegarde introuvable.")
        exit(1)

    purged = purge_old_backups()
    if not purged:
        print("✅ Aucune purge nécessaire. Tous les quotas sont respectés.")
    else:
        print("🧹 Sauvegardes obsolètes supprimées :")
        for zone, filename in purged:
            print(f"  - Zone {zone} ➜ {filename}")
