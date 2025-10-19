# -*- coding: utf-8 -*-
"""
Telemetry Aggregator (S8)
- Centralise et corrèle des métriques/logs d'exploitation (S7→S8)
- Normalise au format: {timestamp, metric, value, source, severity, extra}
- Écrit un JSONL par jour: ops/telemetry/aggregated/YYYY-MM-DD.jsonl

Sources visées (non exhaustif, best-effort, PII-safe):
- tools/reports/monitor.log
- tools/reports/resilience.log
- tools/reports/daily/YYYY-MM-DD/*.log
- ops/alerts.json (compte WARN/CRIT)
- snapshots /debug/eotp-stats (si fournis par appelant)

Ce module n'exécute pas de scripts externes; il lit/agrège des sorties existantes.
Le management command 'telemetry_collect' pilotera la fenêtre (ex: 24h) et fournira
éventuellement un snapshot eotp-stats (via Client GET) en DEV/TEST.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Modèle normalisé (éviter PII)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class TelemetryRecord:
    timestamp: int  # epoch seconds (UTC)
    metric: str  # nom court (snake_case)
    value: float  # valeur numérique (0/1 ou agrégat)
    source: str  # 'monitor', 'resilience', 'alerts', 'stats', ...
    severity: str = "INFO"  # INFO|WARN|CRIT|DEBUG
    extra: Optional[Dict[str, Any]] = None  # métadonnées PII-safe

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────────────────────────
def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_timestamp_from_line(line: str) -> Optional[datetime]:
    """
    Exemples attendus dans nos journaux:
      [2025-10-19T04:12:34Z] MESSAGE ...
    """
    m = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]", line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    except Exception:
        return None


def _severity_from_line(line: str) -> str:
    s = line.upper()
    if " CRIT" in s or "CRIT:" in s or "FAIL" in s:
        return "CRIT"
    if " WARN" in s or "WARN:" in s:
        return "WARN"
    if " OK" in s or "INFO" in s or "NOTE:" in s:
        return "INFO"
    return "DEBUG"


def _within_window(ts: datetime, start: datetime, end: datetime) -> bool:
    return start <= ts <= end


# ──────────────────────────────────────────────────────────────────────────────
# Collecteurs de sources
# ──────────────────────────────────────────────────────────────────────────────
def collect_from_log_file(
    path: Path,
    metric_prefix: str,
    source: str,
    start: datetime,
    end: datetime,
) -> Iterator[TelemetryRecord]:
    """
    Transforme chaque ligne en un point 0/1 avec sévérité, filtré sur la fenêtre.
    """
    if not path.exists():
        return iter(())
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                ts = _parse_timestamp_from_line(line) or _utc_now()
                if not _within_window(ts, start, end):
                    continue
                sev = _severity_from_line(line)
                yield TelemetryRecord(
                    timestamp=int(ts.timestamp()),
                    metric=f"{metric_prefix}_event",
                    value=1.0,
                    source=source,
                    severity=sev,
                    extra={"line": line.strip()[:400]},
                )
    except Exception:
        # best-effort: ne casse jamais la collecte
        return iter(())


def collect_from_daily_folder(
    daily_root: Path, day: datetime, start: datetime, end: datetime
) -> Iterator[TelemetryRecord]:
    """
    Agrège tous les .log du dossier tools/reports/daily/YYYY-MM-DD/
    """
    day_dir = daily_root / day.strftime("%Y-%m-%d")
    if not day_dir.exists():
        return iter(())
    for p in sorted(day_dir.glob("*.log")):
        yield from collect_from_log_file(
            p, metric_prefix="daily", source=f"daily:{p.name}", start=start, end=end
        )


def collect_from_alerts_config(alerts_path: Path, ts: datetime) -> Iterator[TelemetryRecord]:
    """
    Compte le nombre de règles CRIT/WARN configurées (indication de couverture/rigueur).
    NB: ce n'est pas un runtime state, juste une métadonnée utile.
    """
    if not alerts_path.exists():
        return iter(())
    try:
        data = json.loads(alerts_path.read_text(encoding="utf-8"))
    except Exception:
        return iter(())
    crit = 0
    warn = 0
    try:
        for rule in data.get("rules", []):
            sev = str(rule.get("severity", "")).upper()
            if sev == "CRIT":
                crit += 1
            elif sev == "WARN":
                warn += 1
    except Exception:
        pass

    epoch = int(ts.timestamp())
    yield TelemetryRecord(epoch, "alerts_rules_crit", float(crit), "alerts", "INFO")
    yield TelemetryRecord(epoch, "alerts_rules_warn", float(warn), "alerts", "INFO")


def collect_from_stats_snapshot(
    stats: Optional[Dict[str, Any]], ts: Optional[datetime] = None
) -> Iterator[TelemetryRecord]:
    """
    Transforme un snapshot /debug/eotp-stats (dict) en quelques métriques 0/1 ou compteurs.
    Le snapshot est optionnel.
    """
    if not stats:
        return iter(())
    t = ts or _utc_now()
    records: List[TelemetryRecord] = []
    epoch = int(t.timestamp())

    # Exemples d'agrégation: on s'attend à voir des clés simples (compteurs)
    # L'appelant peut fournir un 'summary' déjà packagé.
    for k, v in list(stats.items())[:50]:
        metric = f"stats_{str(k).lower()}"
        try:
            val = float(v)
        except Exception:
            # Encoder les bools comme 0/1
            if isinstance(v, bool):
                val = 1.0 if v else 0.0
            else:
                continue
        records.append(TelemetryRecord(epoch, metric, val, "stats", "INFO"))
    return iter(records)


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────
def aggregate_window(
    repo_root: Path,
    window: timedelta,
    stats_snapshot: Optional[Dict[str, Any]] = None,
    now_utc: Optional[datetime] = None,
) -> List[TelemetryRecord]:
    """
    Construit la liste de points normalisés dans la fenêtre [now - window, now].
    """
    now = now_utc or _utc_now()
    start = now - window
    out: List[TelemetryRecord] = []

    tools_reports = repo_root / "tools" / "reports"
    ops_dir = repo_root / "ops"

    # Logs ponctuels
    out.extend(
        list(collect_from_log_file(tools_reports / "monitor.log", "monitor", "monitor", start, now))
    )
    out.extend(
        list(
            collect_from_log_file(
                tools_reports / "resilience.log", "resilience", "resilience", start, now
            )
        )
    )
    # Logs journaliers
    out.extend(list(collect_from_daily_folder(tools_reports / "daily", now, start, now)))
    # Config alertes (couverture)
    out.extend(list(collect_from_alerts_config(ops_dir / "alerts.json", now)))
    # Snapshot stats (optionnel)
    out.extend(list(collect_from_stats_snapshot(stats_snapshot, now)))
    return out


def write_aggregated_jsonl(
    records: Iterable[TelemetryRecord], output_dir: Path, when: Optional[datetime] = None
) -> Path:
    """
    Écrit les enregistrements en JSONL dans ops/telemetry/aggregated/YYYY-MM-DD.jsonl
    """
    day = (when or _utc_now()).strftime("%Y-%m-%d")
    target_dir = output_dir / "telemetry" / "aggregated"
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{day}.jsonl"
    with out_path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(rec.to_json() + "\n")
    return out_path
