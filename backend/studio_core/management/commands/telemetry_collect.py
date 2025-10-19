# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Management command: telemetry_collect
- Agrège les journaux/rapports de la fenêtre (--window, ex: 24h)
- Écrit ops/telemetry/aggregated/YYYY-MM-DD.jsonl
- Calcule un résumé de tendance et écrit tools/reports/trends/YYYY-MM-DD.json

Usage:
  poetry run python manage.py telemetry_collect --window 24h
  poetry run python manage.py telemetry_collect --window 2h
"""

import argparse
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from studio_core.telemetry.aggregator import aggregate_window, write_aggregated_jsonl
from studio_core.telemetry.trends import summarize_trends_from_records, write_daily_trends


def _parse_window(spec: str) -> timedelta:
    """
    Parse une durée simple: "<N>h" ou "<N>m" ou "<N>d" (heures, minutes, jours).
    """
    s = (spec or "").strip().lower()
    if not s:
        return timedelta(hours=24)
    try:
        if s.endswith("h"):
            return timedelta(hours=int(s[:-1]))
        if s.endswith("m"):
            return timedelta(minutes=int(s[:-1]))
        if s.endswith("d"):
            return timedelta(days=int(s[:-1]))
        # défaut: interpréter comme heures
        return timedelta(hours=int(s))
    except Exception:
        return timedelta(hours=24)


class Command(BaseCommand):
    help = "Collecte la télémétrie d'exploitation (fenêtre glissante) et produit un résumé de tendances."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--window",
            type=str,
            default="24h",
            help="Fenêtre de collecte (ex: 24h, 2h, 90m, 2d). Défaut: 24h",
        )

    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        window = _parse_window(options.get("window", "24h"))
        # Repo root = dossier parent de BASE_DIR (qui est backend/)
        try:
            base_dir = Path(getattr(settings, "BASE_DIR"))
            repo_root = base_dir.parent
        except Exception:
            repo_root = Path.cwd()

        # Optionnel: intégrer un snapshot /debug/eotp-stats (DEV/TEST) ici si nécessaire.
        # Pour une première itération, on n'en fournit pas (stats_snapshot=None).
        self.stdout.write(
            self.style.NOTICE(f"[telemetry_collect] Fenêtre: {window} — repo: {repo_root}")
        )

        records = aggregate_window(repo_root, window, stats_snapshot=None)
        if not records:
            self.stdout.write(
                self.style.WARNING(
                    "[telemetry_collect] Aucun enregistrement collecté dans la fenêtre."
                )
            )
        # Écriture JSONL agrégé
        out_jsonl = write_aggregated_jsonl(records, output_dir=repo_root / "ops")
        self.stdout.write(self.style.SUCCESS(f"[telemetry_collect] Agrégé → {out_jsonl}"))

        # La fonction trends attend des mappings; convertir nos dataclasses si nécessaire.
        # Ici, on sérialise en json puis on re-charge pour obtenir une liste de dicts.
        as_dicts: list[Dict[str, Any]] = []
        for r in records:
            try:
                as_dicts.append(
                    {
                        "timestamp": int(getattr(r, "timestamp", 0)),
                        "metric": str(getattr(r, "metric", "")),
                        "value": float(getattr(r, "value", 0.0)),
                        "source": str(getattr(r, "source", "")),
                        "severity": str(getattr(r, "severity", "INFO")),
                    }
                )
            except Exception:
                continue

        summary = summarize_trends_from_records(as_dicts, window=window)
        out_trends = write_daily_trends(summary, repo_root=repo_root)
        self.stdout.write(self.style.SUCCESS(f"[telemetry_collect] Tendances → {out_trends}"))
        return None
