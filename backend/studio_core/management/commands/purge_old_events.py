# -*- coding: utf-8 -*-
"""
Django management command — purge_old_events

Objectif
- Purger les entrées JSONL anciennes du journal Laby (honeypot) pour respecter
  la rétention (RGPD) et limiter la taille des fichiers.
- Optionnellement sauvegarder les entrées purgées dans un fichier d'archive
  (JSONL) avec compression gzip.

Important (chaînage de hash)
- Le fichier JSONL Laby contient un champ 'chain_hash' par entrée, calculé à
  partir du hash précédent. La purge de lignes anciennes ne recalcule PAS les
  hash. La vérification de chaînage d'un sous-ensemble post-purge suppose de
  connaître le dernier hash de l'historique précédent (ex: disponible via les
  bundles scellés quotidiens). Ce choix évite d'altérer les journaux restants
  tout en respectant la rétention.

Utilisation:
  python manage.py purge_old_events --days 90
  python manage.py purge_old_events --days 30 --jsonl /var/log/laby.jsonl
  python manage.py purge_old_events --days 180 --backup-dir /var/archives/laby --gzip
  python manage.py purge_old_events --days 60 --dry-run

Options:
  --days D                 Nombre de jours à conserver (les entrées STRICTEMENT
                           antérieures au cutoff UTC sont purgées). Par défaut: 90.
  --jsonl PATH             Fichier JSONL source. Défaut: $LABY_JSONL_PATH ou /tmp/laby_events.jsonl
  --backup-dir DIR         Répertoire où écrire les entrées purgées (JSONL).
                           Un nom avec timestamp est généré automatiquement.
  --gzip                   Compresse le backup en .gz (si --backup-dir est fourni).
  --dry-run                N'écrit/réécrit rien; affiche uniquement le bilan.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import tempfile
from typing import Dict, Iterable, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _utcnow() -> dt.datetime:
    # Naive UTC for consistency with ts_utc "Z" naive comparison
    return dt.datetime.utcnow()


def _parse_utc_iso8601(ts: str) -> Optional[dt.datetime]:
    """
    Parse timestamps like "YYYY-MM-DDTHH:MM:SSZ" or with fractional seconds.
    Returns naive datetime assumed to be UTC, or None on failure.
    """
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    # Remove trailing Z/z and trim fractional seconds if present
    if s.endswith(("Z", "z")):
        s = s[:-1]
    if " " in s:
        s = s.replace(" ", "T")
    # Drop fractional seconds if present (keep seconds resolution)
    if "." in s:
        s = s.split(".", 1)[0]
    # Expect at least YYYY-MM-DDTHH:MM:SS
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        # Fallback: date-only support (e.g., "YYYY-MM-DD")
        try:
            d = dt.datetime.strptime(s, "%Y-%m-%d")
            # Normalize to start of day
            return dt.datetime(d.year, d.month, d.day, 0, 0, 0)
        except Exception:
            return None


def _iter_jsonl(path: str) -> Iterable[Tuple[str, Optional[Dict]]]:
    """
    Iterate lines from a JSONL file, yielding (raw_line, parsed_json_or_None).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.rstrip("\n")
                if not raw:
                    yield raw, None
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = None
                yield raw, obj
    except FileNotFoundError:
        raise
    except Exception as e:
        raise CommandError(f"Erreur lecture JSONL: {e}") from e


def _open_backup_writer(backup_dir: str, gzip_enabled: bool) -> Tuple[io.TextIOBase, str]:
    """
    Create a backup JSONL file in backup_dir with a timestamped name.
    Returns (text_writer, file_path). If gzip_enabled, wraps a gzip stream.
    """
    when = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"laby_purged_{when}.jsonl"
    os.makedirs(backup_dir, exist_ok=True)
    dest_path = os.path.join(backup_dir, base_name + (".gz" if gzip_enabled else ""))
    if gzip_enabled:
        gz = gzip.open(dest_path, "wb")
        # Wrap with a TextIO wrapper for writing text lines
        writer = io.TextIOWrapper(gz, encoding="utf-8", newline="\n")
        return writer, dest_path
    else:
        fh = open(dest_path, "w", encoding="utf-8", newline="\n")
        return fh, dest_path


class Command(BaseCommand):
    help = "Purge les anciennes entrées du JSONL Laby selon une politique de rétention (nombre de jours)."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--days",
            dest="days",
            type=int,
            default=90,
            help="Nombre de jours à CONSERVER (les entrées strictement plus anciennes sont purgées). Défaut: 90",
        )
        parser.add_argument(
            "--jsonl",
            dest="jsonl",
            default=_env("LABY_JSONL_PATH", "/tmp/laby_events.jsonl"),
            help="Chemin du fichier JSONL source. Défaut: $LABY_JSONL_PATH ou /tmp/laby_events.jsonl",
        )
        parser.add_argument(
            "--backup-dir",
            dest="backup_dir",
            default=None,
            help="Répertoire d'archive pour les entrées purgées (JSONL). Si omis, aucune sauvegarde n'est faite.",
        )
        parser.add_argument(
            "--gzip",
            dest="gzip",
            action="store_true",
            help="Compresse le fichier d'archive purgée au format gzip (si --backup-dir est fourni).",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Simulation: ne modifie aucun fichier, affiche un bilan uniquement.",
        )

    def handle(self, *args, **opts) -> None:
        days: int = int(opts["days"])
        if days <= 0:
            raise CommandError("--days doit être un entier positif (> 0).")

        jsonl_path: str = str(opts["jsonl"])
        backup_dir: Optional[str] = str(opts["backup_dir"]) if opts["backup_dir"] else None
        gzip_enabled: bool = bool(opts["gzip"])
        dry_run: bool = bool(opts["dry_run"])

        self.stdout.write(self.style.NOTICE(f"Rétention Laby — purge des événements (JSONL):"))
        self.stdout.write(f"- Fichier JSONL: {jsonl_path}")
        self.stdout.write(f"- Conserver: {days} jours (UTC)")
        if backup_dir:
            self.stdout.write(f"- Backup des purgés: {backup_dir} (gzip={gzip_enabled})")
        else:
            self.stdout.write("- Backup des purgés: désactivé")
        self.stdout.write(f"- Mode simulation: {'OUI' if dry_run else 'NON'}")

        try:
            total_lines = 0
            malformed_lines = 0
            kept = 0
            purged = 0

            cutoff_utc = _utcnow() - dt.timedelta(days=days)
            # Normalize cutoff to second resolution to match typical ts_utc
            cutoff_utc = cutoff_utc.replace(microsecond=0)

            # Prepare backup writer if needed
            backup_writer: Optional[io.TextIOBase] = None
            backup_path: Optional[str] = None
            if backup_dir and not dry_run:
                backup_writer, backup_path = _open_backup_writer(backup_dir, gzip_enabled)

            # Prepare temporary file for kept entries
            temp_path: Optional[str] = None
            temp_fh: Optional[io.TextIOBase] = None
            if not dry_run:
                temp_dir = os.path.dirname(os.path.abspath(jsonl_path)) or "."
                fd, temp_path = tempfile.mkstemp(prefix="purge_tmp_", suffix=".jsonl", dir=temp_dir)
                temp_fh = os.fdopen(fd, "w", encoding="utf-8", newline="\n")

            # Iterate and partition
            for raw, obj in _iter_jsonl(jsonl_path):
                total_lines += 1
                if not obj or "ts_utc" not in obj:
                    malformed_lines += 1
                    # Keep malformed lines by default to avoid accidental data loss
                    if not dry_run and temp_fh:
                        temp_fh.write(raw + "\n")
                        kept += 1
                    else:
                        kept += 1
                    continue

                ts = _parse_utc_iso8601(str(obj.get("ts_utc") or ""))
                if ts is None:
                    # Treat as malformed → keep
                    malformed_lines += 1
                    if not dry_run and temp_fh:
                        temp_fh.write(raw + "\n")
                        kept += 1
                    else:
                        kept += 1
                    continue

                if ts < cutoff_utc:
                    # Old entry → purge
                    purged += 1
                    if backup_writer and not dry_run:
                        backup_writer.write(raw + "\n")
                else:
                    # Keep entry
                    kept += 1
                    if not dry_run and temp_fh:
                        temp_fh.write(raw + "\n")

            # Close writers
            if backup_writer:
                try:
                    backup_writer.flush()
                    # If backup_writer is a TextIOWrapper over gzip, closing wrapper closes gzip too
                    backup_writer.close()
                except Exception:
                    pass
            if temp_fh:
                try:
                    temp_fh.flush()
                    temp_fh.close()
                except Exception:
                    pass

            # Replace original file atomiquement si pas dry-run
            if not dry_run and temp_path:
                try:
                    os.replace(temp_path, jsonl_path)
                except Exception as e:
                    # Cleanup temp file on failure
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                    raise CommandError(f"Échec du remplacement du fichier JSONL: {e}") from e

            # Bilan
            self.stdout.write(
                self.style.SUCCESS("Purge terminée." if not dry_run else "Simulation terminée.")
            )
            self.stdout.write(f"- Total lignes lues: {total_lines}")
            self.stdout.write(f"- Malformées (conservées): {malformed_lines}")
            self.stdout.write(f"- Conservées: {kept}")
            self.stdout.write(f"- Purgées: {purged}")
            self.stdout.write(f"- Cutoff UTC: {cutoff_utc.isoformat()}Z")
            if backup_path and purged > 0 and not dry_run:
                self.stdout.write(self.style.NOTICE(f"- Backup: {backup_path}"))
            if not dry_run and purged == 0:
                self.stdout.write("- Aucune ligne à purger selon ce cutoff.")

        except FileNotFoundError:
            raise CommandError(f"Fichier JSONL introuvable: {jsonl_path}")
        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f"Erreur lors de la purge: {e}") from e
