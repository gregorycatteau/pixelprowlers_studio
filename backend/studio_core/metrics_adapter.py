# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Tuple


class _InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        # histograms stored as name -> {"count": int, "sum": float}
        self._hists: Dict[str, Dict[str, float]] = {}

    def counter_inc(self, name: str, labels: Dict[str, Any] | None = None, n: int = 1) -> None:
        """
        Increment a named counter by n.
        Labels are currently ignored for aggregation stability (append-only logs can include them).
        """
        if not isinstance(n, int):
            try:
                n = int(n)
            except Exception:
                n = 1
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + n

    def histogram_observe(
        self, name: str, value: float, labels: Dict[str, Any] | None = None
    ) -> None:
        """
        Observe a value in a named histogram (count/sum only; quantiles not computed here).
        """
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

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            # shallow copy to avoid external mutation
            return {
                "ts": int(time.time()),
                "counters": dict(self._counters),
                "histograms": {k: dict(v) for k, v in self._hists.items()},
            }


_metrics = _InMemoryMetrics()


def counter_inc(name: str, labels: Dict[str, Any] | None = None, n: int = 1) -> None:
    _metrics.counter_inc(name, labels=labels, n=n)


def histogram_observe(name: str, value: float, labels: Dict[str, Any] | None = None) -> None:
    _metrics.histogram_observe(name, value, labels=labels)


def get_snapshot() -> Dict[str, Any]:
    return _metrics.snapshot()
