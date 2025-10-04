from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# === IMPORT LOGGER ===
from backup_event_logger import log_event
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# === CONST PATHS ===
BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
CDN_ZONES_DIR = BACKEND_ROOT / "cdn_zones"
BACKUPS_DIR = BACKEND_ROOT / ".context_backups"
ENV_FILE = BACKEND_ROOT / ".env.development"


def _sanitize_zone_filename(name: str) -> str:
    """
    N'accepte que des noms de fichiers .json sans séparateurs de chemin.
    """
    p = Path(name)
    if p.name != name:
        raise ValueError("Chemin invalide (nom de fichier uniquement, sans répertoires)")
    if p.suffix.lower() != ".json":
        raise ValueError("Seuls les fichiers .json sont autorisés")
    return name


def _safe_join(base: Path, rel_name: str) -> Path:
    """
    Jointure sûre: résout et vérifie que le chemin reste confiné dans 'base'.
    """
    target = (base / rel_name).resolve()
    target.relative_to(base)
    return target


def _load_backup_key() -> bytes:
    """
    Charge BACKUP_KEY depuis l'environnement, avec support facultatif du fichier .env.development.
    """
    # Charge .env.development s'il existe (facultatif)
    if ENV_FILE.exists():
        try:
            load_dotenv(dotenv_path=str(ENV_FILE))
        except Exception:
            # Ne pas casser le script si dotenv échoue; on tente l'env direct
            pass

    key = os.getenv("BACKUP_KEY", "").strip()
    if not key:
        raise RuntimeError("BACKUP_KEY manquante (définis-la dans l'env ou .env.development)")
    return key.encode("utf-8")


def backup(zone_file: str) -> tuple[Path, Path]:
    """
    Chiffre le fichier JSON (cdn_zones/<zone_file>) et écrit:
      - un binaire chiffré (.bin)
      - un manifest JSON (.json) avec hash SHA-256
    Retourne les chemins (binaire, manifest).
    """
    safe_name = _sanitize_zone_filename(zone_file)
    zone_path = _safe_join(CDN_ZONES_DIR, safe_name)
    if not zone_path.is_file():
        raise FileNotFoundError(f"Fichier introuvable dans cdn_zones/: {safe_name}")

    fernet = Fernet(_load_backup_key())

    data = zone_path.read_bytes()
    encrypted = fernet.encrypt(data)
    file_hash = hashlib.sha256(encrypted).hexdigest()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    zone_name = zone_path.stem
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    output_path = BACKUPS_DIR / f"{zone_name}__{timestamp}.bin"
    manifest_path = BACKUPS_DIR / f"{zone_name}__{timestamp}.json"

    output_path.write_bytes(encrypted)
    manifest = {
        "zone": zone_name,
        "original_file": safe_name,
        "timestamp_utc": timestamp,
        "encrypted_file": output_path.name,
        "hash_sha256": file_hash,
        "backup_agent": "backup_encryptor.py",
        "context_source": "cdn_zones/",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Log structuré de l'opération
    log_event(
        operation="backup",
        zone=zone_name,
        status="success",
        timestamp=timestamp,
        details={
            "manifest_file": manifest_path.name,
            "encrypted_file": output_path.name,
            "hash": file_hash,
        },
    )

    return output_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="backup_encryptor",
        description="Chiffre un fichier JSON dans backend/cdn_zones/",
    )
    parser.add_argument(
        "zone_file",
        help="Nom du fichier .json présent dans cdn_zones/ (ex: Z1.json)",
    )
    args = parser.parse_args()
    try:
        out_path, manifest_path = backup(args.zone_file)
        print(f"\n✅ Sauvegarde réussie : {out_path.name}")
        print(f"📄 Manifest associé : {manifest_path.name}")
        return 0
    except Exception as e:
        print(f"❌ Échec de la sauvegarde: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
