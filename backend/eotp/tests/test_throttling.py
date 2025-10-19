# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from eotp.limits import (
    backoff_get_retry_after,
    backoff_on_failure,
    backoff_reset,
    check_and_consume,
    get_ip_prefix,
)


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


def test_get_ip_prefix_ipv4(rf):
    req = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.42")
    assert get_ip_prefix(req) == "203.0.113"


def test_get_ip_prefix_ipv6(rf):
    req = rf.get("/", HTTP_X_FORWARDED_FOR="2001:db8:85a3::8a2e:370:7334")
    # first hextets truncated
    pref = get_ip_prefix(req)
    assert ":" in pref
    assert pref.startswith("2001:db8:")
    # 3rd/4th hextet present (pii-safe enough)
    assert len(pref.split(":")) == 4


def test_fixed_window_ratelimit_fallback_allows_then_blocks(monkeypatch):
    # Ensure env defaults (5/min verify)
    monkeypatch.setenv("RATELIMIT_ENABLE", "1")
    monkeypatch.setenv("RATELIMIT_TTL_VERIFY", "60")
    monkeypatch.setenv("RATELIMIT_BUCKET_VERIFY", "3")  # make it small for test
    # Use stable scopes (no real user/session needed)
    scopes = {"ip": "203.0.113", "session": "sess-abc", "user": "u1"}

    # First 3 allowed
    for i in range(3):
        allowed, retry = check_and_consume("verify", scopes)
        assert allowed is True
        assert retry >= 0

    # 4th should be blocked with retry_after <= ttl
    allowed, retry = check_and_consume("verify", scopes)
    assert allowed is False
    assert 0 <= retry <= 60


def test_backoff_progression_and_reset():
    sess = "sess-backoff"
    # Initially no backoff
    assert backoff_get_retry_after(sess) == 0

    # First failure -> 1s
    d1 = backoff_on_failure(sess)
    assert d1 == 1
    assert 0 <= backoff_get_retry_after(sess) <= 1

    # Second failure -> 2s (cap progression)
    d2 = backoff_on_failure(sess)
    assert d2 == 2
    after = backoff_get_retry_after(sess)
    assert 1 <= after <= 2

    # Reset clears state (simulates success)
    backoff_reset(sess)
    assert backoff_get_retry_after(sess) == 0


@override_settings(APP_ENV="test")
def test_debug_eotp_stats_endpoint_returns_snapshot_in_test_env(client: Client):
    # APP_ENV=test → endpoint should be available
    resp = client.get("/debug/eotp-stats")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is True
    stats = payload.get("stats") or {}
    assert "ts" in stats
    assert "counters" in stats
    assert "histograms" in stats
