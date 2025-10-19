# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Runtime telemetry helpers (S8)

Objectif:
- Lire le dernier résumé de tendances (tools/reports/trends/YYYY-MM-DD.json)
- Exposer un helper pour obtenir le risk_operational_score courant
- Proposer une adaptation ±10% d'un seuil (ex: GATE_RISK_THRESHOLD)

Notes:
- PII-safe, best-effort: en cas d'erreur, retourne None/valeur par défaut.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _repo_root() -> Path:
    """
    Déduit la racine du repo en remontant depuis ce fichier:
    backend/studio_core/telemetry/runtime.py → <repo_root>
    """
    return Path(__file__).resolve().parents[3]


def _latest_trends_path(repo_root: Optional[Path] = None) -> Optional[Path]:
    root = repo_root or _repo_root()
    trends_dir = root / "tools" / "reports" / "trends"
    if not trends_dir.exists():
        return None
    # Trier par nom (YYYY-MM-DD.json), puis prendre le plus récent
    files = sorted(trends_dir.glob("*.json"))
    return files[-1] if files else None


def get_latest_trends_summary(repo_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Charge le JSON du jour le plus récent sous tools/reports/trends/.
    Retourne un dict ou None si indisponible/erreur.
    """
    path = _latest_trends_path(repo_root)
    if not path:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "risk_operational_score" in data:
            return data
    except Exception:
        pass
    return None


def get_latest_risk_score(repo_root: Optional[Path] = None) -> Optional[float]:
    """
    Retourne le risk_operational_score du dernier résumé disponible, ou None.
    """
    summ = get_latest_trends_summary(repo_root)
    if not summ:
        return None
    try:
        v = float(summ.get("risk_operational_score"))
        # bornes de sécurité
        return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
    except Exception:
        return None


def adaptive_threshold(base: float, risk_operational_score: Optional[float]) -> float:
    """
    Applique une adaptation ±10% d'un seuil 'base' selon le score opérationnel:
    - score >= 0.7 → renforcer: +10%
    - score <= 0.3 → relâcher:  -10%
    - sinon, inchangé

    Retourne un seuil borné dans [0,1].
    """
    if risk_operational_score is None:
        return max(0.0, min(1.0, base))
    if risk_operational_score >= 0.7:
        out = base * 1.10
    elif risk_operational_score <= 0.3:
        out = base * 0.90
    else:
        out = base
    # Bornage
    if out < 0.0:
        out = 0.0
    if out > 1.0:
        out = 1.0
    return out
