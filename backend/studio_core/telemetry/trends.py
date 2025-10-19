# -*- coding: utf-8 -*-
"""
Telemetry Trends (S8)
- Analyse de tendance sur les enregistrements agrégés (voir telemetry.aggregator)
- Calcule moyennes mobiles, écarts-types et un score de dérive/risque opérationnel (0..1)
- Produit un résumé journalier JSON: tools/reports/trends/YYYY-MM-DD.json

Heuristique simple (PII-safe, best-effort):
- Pondère CRIT > WARN > INFO
- Normalise par le volume total d'événements de la fenêtre
- Détecte une dérive si (taux_pondéré - moyenne_mobile) > k * écart_type
- risk_operational_score ∈ [0,1] := clamp(taux_pondéré * facteur_anomalie)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass
class TrendPoint:
    ts: int
    weighted_rate: float  # [0..1]
    total_events: int
    crit: int
    warn: int
    info: int


@dataclass
class TrendSummary:
    day: str
    window_seconds: int
    moving_avg: float
    moving_std: float
    last_weighted_rate: float
    drift_detected: bool
    risk_operational_score: float
    totals: Dict[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _weights_for_severity(sev: str) -> float:
    s = (sev or "").upper()
    if s == "CRIT":
        return 1.0
    if s == "WARN":
        return 0.5
    return 0.1  # INFO/DEBUG


def _bucketize(
    records: Iterable[Mapping[str, Any]], bucket_seconds: int = 3600
) -> List[TrendPoint]:
    """
    Regroupe les enregistrements par tranches fixes (par défaut 1h) et calcule un taux pondéré.
    """
    buckets: Dict[int, Dict[str, Any]] = {}
    for r in records:
        ts = int(r.get("timestamp", 0)) or 0
        sev = str(r.get("severity", "INFO"))
        b = (ts // bucket_seconds) * bucket_seconds
        slot = buckets.setdefault(b, {"crit": 0, "warn": 0, "info": 0, "w_sum": 0.0, "n": 0})
        if sev.upper() == "CRIT":
            slot["crit"] += 1
        elif sev.upper() == "WARN":
            slot["warn"] += 1
        else:
            slot["info"] += 1
        slot["w_sum"] += _weights_for_severity(sev)
        slot["n"] += 1

    points: List[TrendPoint] = []
    for b in sorted(buckets.keys()):
        slot = buckets[b]
        n = int(slot["n"])
        w_rate = float(slot["w_sum"]) / float(n) if n > 0 else 0.0
        points.append(
            TrendPoint(
                ts=b,
                weighted_rate=max(0.0, min(1.0, w_rate)),
                total_events=n,
                crit=int(slot["crit"]),
                warn=int(slot["warn"]),
                info=int(slot["info"]),
            )
        )
    return points


def compute_moving_stats(values: List[float], window: int = 6) -> Tuple[float, float]:
    """
    Retourne (moyenne_mobile, écart_type_population) sur les 'window' derniers points.
    Si pas assez de points, utilise ce qui est disponible (min 1).
    """
    if not values:
        return 0.0, 0.0
    tail = values[-window:] if len(values) >= window else values[:]
    avg = mean(tail)
    std = pstdev(tail) if len(tail) >= 2 else 0.0
    return float(avg), float(std)


def detect_trend_and_score(
    points: List[TrendPoint], window_seconds: int, drift_k: float = 2.0
) -> TrendSummary:
    """
    Détecte une dérive et calcule un score de risque opérationnel [0..1].
    - drift si (dernier - moyenne_mobile) > k * std
    - risk_score := clamp(dernier * (1.0 + 0.25 * is_drift))
    """
    weighted = [p.weighted_rate for p in points]
    avg, std = compute_moving_stats(
        weighted, window=max(3, min(24, int(window_seconds // 3600) or 3))
    )
    last = weighted[-1] if weighted else 0.0
    drift = (std > 0.0) and ((last - avg) > (drift_k * std))
    score = max(0.0, min(1.0, last * (1.25 if drift else 1.0)))

    totals = {
        "crit": sum(p.crit for p in points),
        "warn": sum(p.warn for p in points),
        "info": sum(p.info for p in points),
        "events": sum(p.total_events for p in points),
    }
    return TrendSummary(
        day=_utc_now().strftime("%Y-%m-%d"),
        window_seconds=int(window_seconds),
        moving_avg=float(avg),
        moving_std=float(std),
        last_weighted_rate=float(last),
        drift_detected=bool(drift),
        risk_operational_score=float(score),
        totals=totals,
    )


def summarize_trends_from_records(
    records: Iterable[Mapping[str, Any]], window: timedelta
) -> TrendSummary:
    pts = _bucketize(records)
    return detect_trend_and_score(pts, window_seconds=int(window.total_seconds()))


def write_daily_trends(
    summary: TrendSummary, repo_root: Path, when: Optional[datetime] = None
) -> Path:
    """
    Écrit le résumé JSON dans tools/reports/trends/YYYY-MM-DD.json
    """
    day = (when or _utc_now()).strftime("%Y-%m-%d")
    out_dir = repo_root / "tools" / "reports" / "trends"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{day}.json"
    out_path.write_text(summary.to_json(), encoding="utf-8")
    return out_path
