import json
import os
from datetime import datetime
from pathlib import Path

# === CONFIGURATION ===
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
BACKUP_DIR = PROJECT_ROOT / ".context_backups"
MAX_VERSIONS_PER_ZONE = 3  # Nombre maximum de versions à conserver


def rotate_backups_for_zone(zone_name):
    """
    Supprime les sauvegardes les plus anciennes (FIFO) si le nombre max est dépassé.
    """
    backups = []

    for f in os.listdir(BACKUP_DIR):
        if f.startswith(zone_name + "__") and f.endswith(".bin"):
            full_path = BACKUP_DIR / f
            try:
                timestamp_str = f.split("__")[1].replace(".bin", "")
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d-%H%M%S")
                backups.append((timestamp, full_path))
            except Exception:
                continue  # On ignore les formats incorrects

    backups.sort(key=lambda x: x[0])  # Tri du plus ancien au plus récent

    while len(backups) > MAX_VERSIONS_PER_ZONE:
        old_backup_path = backups.pop(0)[1]
        old_manifest_path = old_backup_path.with_suffix(".json")

        try:
            os.remove(old_backup_path)
            if old_manifest_path.exists():
                os.remove(old_manifest_path)
            print(f"🗑️ Ancienne sauvegarde supprimée : {old_backup_path.name}")
        except Exception as e:
            print(f"❌ Erreur lors de la suppression de {old_backup_path.name} : {e}")


def rotate_all_zones():
    """
    Lance la rotation pour chaque zone trouvée dans le dossier de sauvegarde.
    """
    seen_zones = set()
    for f in os.listdir(BACKUP_DIR):
        if f.endswith(".bin") and "__" in f:
            zone = f.split("__")[0]
            if zone not in seen_zones:
                rotate_backups_for_zone(zone)
                seen_zones.add(zone)


if __name__ == "__main__":
    rotate_all_zones()
