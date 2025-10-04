from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# Import interne (module local, sûr)
from backup_event_logger import log_event
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Répertoires de travail ancrés sur le backend
BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
BACKUPS_DIR = BACKEND_ROOT / ".context_backups"
CDN_ZONES_DIR = BACKEND_ROOT / "cdn_zones"
ENV_FILE = BACKEND_ROOT / ".env.development"


def _sanitize_bin_filename(name: str) -> str:
    """
    Accepte uniquement un nom de fichier .bin sans séparateurs.
    Empêche toute traversée de chemin.
    """
    p = Path(name)
    if p.name != name:
        raise ValueError("Nom de fichier invalide (pas de répertoires)")
    if p.suffix.lower() != ".bin":
        raise ValueError("Seuls les fichiers .bin sont autorisés")
    return name


def _sanitize_zone_filename(name: str) -> str:
    """
    Accepte uniquement un nom de fichier .json sans séparateurs.
    """
    p = Path(name)
    if p.name != name:
        raise ValueError("Nom de fichier invalide (pas de répertoires)")
    if p.suffix.lower() != ".json":
        raise ValueError("Seuls les fichiers .json sont autorisés")
    return name


def _safe_join(base: Path, rel_name: str) -> Path:
    """
    Jointure sûre: résout et vérifie le confinement dans 'base'.
    """
    target = (base / rel_name).resolve()
    target.relative_to(base)
    return target


def _load_backup_key() -> bytes:
    """
    Charge BACKUP_KEY via l'environnement; charge .env.development si présent.
    """
    if ENV_FILE.exists():
        try:
            load_dotenv(dotenv_path=str(ENV_FILE))
        except Exception:
            # Ne pas casser l'exécution si le .env est illisible
            pass

    key = os.getenv("BACKUP_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "BACKUP_KEY manquante (définis-la dans l'environnement ou .env.development)"
        )
    return key.encode("utf-8")


def restore(bin_file: str) -> Tuple[Path, Path]:
    """
    Déchiffre un fichier .bin depuis .context_backups/ et restaure le JSON dans cdn_zones/.
    Retourne (restored_path, manifest_path).
    """
    safe_bin = _sanitize_bin_filename(bin_file)
    bin_path = _safe_join(BACKUPS_DIR, safe_bin)
    if not bin_path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {bin_path}")

    # Manifest associé
    manifest_path = bin_path.with_suffix(".json")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest introuvable: {manifest_path}")

    encrypted_data = bin_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    expected_hash = manifest.get("hash_sha256")
    computed_hash = hashlib.sha256(encrypted_data).hexdigest()
    zone_name = manifest.get("zone", "unknown")
    timestamp = manifest.get("timestamp_utc", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))

    # Vérification d'intégrité
    if expected_hash != computed_hash:
        log_event(
            operation="restore",
            zone=zone_name,
            status="failed",
            timestamp=timestamp,
            details={
                "error": "hash_mismatch",
                "bin_file": safe_bin,
                "expected": expected_hash,
                "computed": computed_hash,
            },
        )
        raise ValueError("Hash manifest != hash du binaire (fichier corrompu/modifié)")

    # Déchiffrement
    fernet = Fernet(_load_backup_key())
    try:
        decrypted_data = fernet.decrypt(encrypted_data)
    except Exception as e:
        log_event(
            operation="restore",
            zone=zone_name,
            status="failed",
            timestamp=timestamp,
            details={"error": str(e), "bin_file": safe_bin},
        )
        raise

    # Écriture du fichier restauré (sécurisé)
    zone_file = _sanitize_zone_filename(manifest["original_file"])
    restored_path = _safe_join(CDN_ZONES_DIR, zone_file)
    restored_path.write_bytes(decrypted_data)

    log_event(
        operation="restore",
        zone=zone_name,
        status="success",
        timestamp=timestamp,
        details={"restored_file": zone_file, "manifest": manifest_path.name},
    )

    return restored_path, manifest_path


def _validate_restored(restored_path: Path, zone_name: str) -> None:
    """
    Validation post-restauration via validate_file si disponible.
    Écrit des logs d'état; n'élève pas d'exception fatale.
    """
    # Import paresseux et local, sans toucher sys.path global à l'import
    import sys

    try:
        if str(BACKEND_ROOT) not in sys.path:
            sys.path.insert(0, str(BACKEND_ROOT))
        from overall_context.validators.post_restore_validator import validate_file  # type: ignore
    except Exception as e:
        # Validation indisponible — on journalise et on continue
        log_event(
            operation="restore_validation",
            zone=zone_name,
            status="error",
            timestamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
            details={
                "error": f"validator_import_failed: {e}",
                "file": str(restored_path),
            },
        )
        print(f"❌ Validator import failed: {e}")
        return

    try:
        schema_path = BACKEND_ROOT / "overall_context" / "data" / "cdn_schema_operational_v1.json"
        result, messages = validate_file(str(restored_path), str(schema_path))

        for msg in messages:
            print("🔹", msg)

        if not result:
            log_event(
                operation="restore_validation",
                zone=zone_name,
                status="warning",
                timestamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
                details={"file": restored_path.name, "issues": messages},
            )
            print("⚠️ Validation terminée avec des avertissements.")
        else:
            print("✅ Validation complète réussie.")
    except Exception as e:
        log_event(
            operation="restore_validation",
            zone=zone_name,
            status="error",
            timestamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
            details={"error": str(e), "file": restored_path.name},
        )
        print(f"❌ Erreur pendant la validation post-restauration : {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="restore_decryptor",
        description="Restaure un backup chiffré (.bin) vers cdn_zones/ après vérification d'intégrité.",
    )
    parser.add_argument("bin_file", help="Nom du fichier .bin dans .context_backups/")
    args = parser.parse_args()

    try:
        restored_path, manifest_path = restore(args.bin_file)
        print(f"\n✅ Fichier restauré : {restored_path.name}")
        print(f"📁 Localisation : cdn_zones/{restored_path.name}")
        print("\n🔍 Validation post-restauration en cours...")
        # Récupération du zone_name via manifest pour la journalisation
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_restored(restored_path, manifest.get("zone", "unknown"))
        return 0
    except Exception as e:
        print(f"❌ Échec de la restauration: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
