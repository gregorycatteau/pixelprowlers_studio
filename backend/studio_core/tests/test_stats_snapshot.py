# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from django.test import Client, override_settings
from studio_core.metrics_backend import counter_inc, histogram_observe


@override_settings(APP_ENV="test")
def test_debug_eotp_stats_snapshot_contains_expected_counters():
    """
    Exerce quelques compteurs/Histogrammes via l'adapter métriques, puis
    vérifie que /debug/eotp-stats expose un snapshot contenant ces clés.
    """
    # Arrange: incrémenter des compteurs attendus par S6
    counter_inc("eotp_issue_total", n=2)
    counter_inc("eotp_ok_total", n=1)
    counter_inc("eotp_failed_total", n=1)
    counter_inc("eotp_resend_429_total", n=1)
    histogram_observe("eotp_issue_to_ok_seconds", 0.42)
    histogram_observe("eotp_issue_to_ok_seconds", 1.23)

    # Act: appeler l'endpoint debug (DEV/TEST only)
    client = Client()
    resp = client.get("/debug/eotp-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True

    stats = body.get("stats") or {}
    counters = stats.get("counters") or {}
    histos = stats.get("histograms") or {}

    # Assert counters exist with at least the values we set
    assert counters.get("eotp_issue_total", 0) >= 2
    assert counters.get("eotp_ok_total", 0) >= 1
    assert counters.get("eotp_failed_total", 0) >= 1
    assert counters.get("eotp_resend_429_total", 0) >= 1

    # Assert histogram shape (count/sum present)
    h = histos.get("eotp_issue_to_ok_seconds") or {}
    assert isinstance(h, dict)
    assert h.get("count", 0) >= 2
    assert h.get("sum", 0.0) >= 1.65  # 0.42 + 1.23 = 1.65
