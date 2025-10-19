# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Management command: seal_day
- Scelle le journal quotidien via hash-chain + HMAC (HMAC-SHA256)
- Écrit une preuve texte: ops/reports/seals/YYYY-MM-DD.txt

Usage:
  poetry run python manage.py seal_day --date 2025-10-19
  poetry run python manage.py seal_day            # scelle le jour courant (UTC)

Options:
  --date YYYY-MM-DD      (facultatif) jour à sceller
  --file /path/to/log    (facultatif) chemin du journal à sceller
  --key  secretvalue     (facultatif) clé HMAC; sinon OPS_SIGNING_KEY (env)
"""

from pathlib import Path
from typing import Any, Optional

from django.core.management.base import BaseCommand, CommandParser
from studio_core.obs.journal import seal_day as seal_day_impl


class Command(BaseCommand):
    help = "Scelle le journal quotidien (hash-chain + HMAC) et écrit une preuve sous ops/reports/seals/."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Jour à sceller au format YYYY-MM-DD (défaut: aujourd'hui UTC)",
        )
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Chemin du fichier journal (par défaut OBS_JOURNAL_FILE ou <BASE_DIR>/var/auth_journal.log)",
        )
        parser.add_argument(
            "--key",
            type=str,
            default=None,
            help="Clé HMAC (fallback: OPS_SIGNING_KEY dans l'environnement)",
        )

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        day = options.get("date") or None
        file_path = options.get("file") or None
        signing_key = options.get("key") or None

        proof_path: Path = seal_day_impl(signing_key=signing_key, date=day, file_path=file_path)
        self.stdout.write(self.style.SUCCESS(f"[seal_day] Proof written → {proof_path}"))
        try:
            # Print small snippet for convenience
            snippet = "\n".join(proof_path.read_text(encoding="utf-8").splitlines()[:4])
            self.stdout.write(self.style.NOTICE(snippet))
        except Exception:
            pass
        return None
