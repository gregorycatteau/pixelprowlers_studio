# -*- coding: utf-8 -*-
from __future__ import annotations

"""
PrometheusAdapter (stub, adapter-first)

But: fournir la même interface que metrics_adapter (counter_inc, histogram_observe, get_snapshot)
sans imposer l'installation/activation de prometheus_client. Prêt pour un branchement
ultérieur en S6+ sans refactor des appelants.

Implémentation actuelle:
- Stockage en mémoire (thread-safe) identique à l'adapter in-memory
- Futur: si prometheus_client est dispo et METRICS_EXPORTER=prometheus, exposer des métriques natives
- get_snapshot() disponible pour /debug/eotp-stats (DEV/TEST)

Env attendus (futurs, non requis pour l'instant):
- METRICS_EXPORTER=prometheus|none
"""

import threading
import time
from typing import Any, Dict

try:
    import prometheus_client  # type: ignore

    _HAS_PROM = True
except Exception:
    _HAS_PROM = False


class _PromBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._hists: Dict[str, Dict[str, float]] = {}

        # Espace réservé pour intégrer prometheus_client ultérieurement
        self._prom_counters: Dict[str, "prometheus_client.Counter"] = {} if _HAS_PROM else {}
        self._prom_hists: Dict[str, "prometheus_client.Histogram"] = {} if _HAS_PROM else {}

    def counter_inc(self, name: str, labels: Dict[str, Any] | None = None, n: int = 1) -> None:
        # Phase 1: agrégation simple (labels ignorés)
        if not isinstance(n, int):
            try:
                n = int(n)
            except Exception:
                n = 1
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + n

        # Phase 2 (future): si _HAS_PROM, incrémenter un Counter Prometheus par labelset

    def histogram_observe(
        self, name: str, value: float, labels: Dict[str, Any] | None = None
    ) -> None:
        try:
            v = float(value)
        except Exception:
            return
        with self._lock:
            h = self._hists.get(name)
            if not h:
                h = {"count": 0.0, "sum": 0.0}
                self._hists[name] = h
            h["count"] += 1.0
            h["sum"] += v

        # Phase 2 (future): si _HAS_PROM, observer sur un Histogram Prometheus

    def get_snapshot(self) -> Dict[str, Any]:
        # Utilisé par /debug/eotp-stats (DEV/TEST). Jamais activé en prod.
        with self._lock:
            return {
                "ts": int(time.time()),
                "counters": dict(self._counters),
                "histograms": {k: dict(v) for k, v in self._hists.items()},
            }


_backend = _PromBackend()


def counter_inc(name: str, labels: Dict[str, Any] | None = None, n: int = 1) -> None:
    _backend.counter_inc(name, labels=labels, n=n)


def histogram_observe(name: str, value: float, labels: Dict[str, Any] | None = None) -> None:
    _backend.histogram_observe(name, value, labels=labels)


def get_snapshot() -> Dict[str, Any]:
    return _backend.get_snapshot()
