# -*- coding: utf-8 -*-
from __future__ import annotations

"""
metrics_backend: sélecteur d’adapter métriques (adapter-first, prom-ready)

Exporte la même interface que metrics_adapter:
- counter_inc(name, labels=None, n=1)
- histogram_observe(name, value, labels=None)
- get_snapshot() -> dict

Sélection via METRICS_BACKEND:
- "prometheus" -> studio_core.metrics_prom
- (défaut) -> studio_core.metrics_adapter
"""

import os
from typing import Any, Dict

_BACKEND = (os.getenv("METRICS_BACKEND") or "inmemory").strip().lower()

if _BACKEND == "prometheus":
    try:
        from .metrics_prom import counter_inc as _counter_inc
        from .metrics_prom import get_snapshot as _get_snapshot
        from .metrics_prom import histogram_observe as _histogram_observe
    except Exception:
        # Fallback silencieux si prom indisponible
        from .metrics_adapter import counter_inc as _counter_inc  # type: ignore
        from .metrics_adapter import get_snapshot as _get_snapshot  # type: ignore
        from .metrics_adapter import histogram_observe as _histogram_observe  # type: ignore
else:
    from .metrics_adapter import counter_inc as _counter_inc  # type: ignore
    from .metrics_adapter import get_snapshot as _get_snapshot  # type: ignore
    from .metrics_adapter import histogram_observe as _histogram_observe  # type: ignore


def counter_inc(name: str, labels: Dict[str, Any] | None = None, n: int = 1) -> None:
    _counter_inc(name, labels=labels, n=n)


def histogram_observe(name: str, value: float, labels: Dict[str, Any] | None = None) -> None:
    _histogram_observe(name, value, labels=labels)


def get_snapshot() -> Dict[str, Any]:
    return _get_snapshot()
