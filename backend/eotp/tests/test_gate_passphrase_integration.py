# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import time

import pytest

pytestmark = pytest.mark.django_db
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


def _csrf_headers(client: Client) -> dict:
    resp = client.get("/csrf/")
    assert resp.status_code == 200
    token = (resp.json() or {}).get("csrfToken")
    assert token
    return {"HTTP_X_CSRFTOKEN": token}


def _create_superuser(username="alice", email="alice@example.com", password="Test#1234"):
    u = User.objects.create_user(
        username=username, email=email, password=password, is_superuser=True
    )
    return u, username, password


@override_settings(APP_ENV="test")
def test_gate_required_blocks_verify_until_passed(monkeypatch):
    """
    risk > threshold -> gate required, verify 403 until /gate/verify ok,
    then resend -> peek -> verify OK (happy after gate).
    """
    client = Client()
    headers = _csrf_headers(client)

    # Enable gate and set TTL
    monkeypatch.setenv("GATE_ENABLE", "1")
    monkeypatch.setenv("GATE_RISK_THRESHOLD", "0.75")
    monkeypatch.setenv("GATE_CACHE_TTL", "60")  # standard

    # Create user (superuser => e-OTP)
    u, username, password = _create_superuser()

    # Login with high risk override header to force gate_required=True
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
        HTTP_X_RISK_OVERRIDE="0.90",
        **headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("status") == "pending_2fa"
    assert payload.get("fa_required") is True
    assert payload.get("gate_required") is True

    # Try verify without solving gate -> 403 generic
    resp = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": "000000"}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 403

    # Issue gate challenge (required True with prompt)
    resp = client.post(
        "/api/auth/2fa/gate/issue/",
        data="{}",
        content_type="application/json",
        HTTP_X_RISK_OVERRIDE="0.90",
        **headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("required") is True
    prompt = data.get("prompt") or ""
    # Parse "a + b = ?"
    m = re.search(r"(\d+)\s*\+\s*(\d+)", prompt)
    assert m
    a, b = int(m.group(1)), int(m.group(2))
    answer = str(a + b)

    # Verify gate with computed answer
    resp = client.post(
        "/api/auth/2fa/gate/verify/",
        data=json.dumps({"response": answer}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("ok") is True

    # Now resend should be allowed (gate_ok=True)
    resp = client.post(
        "/api/auth/2fa/email/resend/",
        data="{}",
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    meta = resp.json()
    assert meta.get("ok") is True
    assert "expires_in" in meta

    # Peek current code (test-only)
    resp = client.post("/api/auth/2fa/email/_peek/", data="{}", content_type="application/json")
    assert resp.status_code == 200
    code = (resp.json() or {}).get("code")
    assert code and len(code) == 6

    # Verify with correct code -> 200 ok (JWT issued)
    resp = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": code}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("ok") is True
    assert "access" in resp.json()


@override_settings(APP_ENV="test")
def test_gate_ttl_expired_returns_403(monkeypatch):
    """
    Gate challenge expires by TTL: verify returns 403 generic.
    """
    client = Client()
    headers = _csrf_headers(client)

    monkeypatch.setenv("GATE_ENABLE", "1")
    monkeypatch.setenv("GATE_RISK_THRESHOLD", "0.75")
    monkeypatch.setenv("GATE_CACHE_TTL", "1")  # very short TTL

    u, username, password = _create_superuser()

    # Login with high risk
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
        HTTP_X_RISK_OVERRIDE="0.90",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("gate_required") is True

    # Issue challenge
    resp = client.post(
        "/api/auth/2fa/gate/issue/",
        data="{}",
        content_type="application/json",
        HTTP_X_RISK_OVERRIDE="0.90",
        **headers,
    )
    assert resp.status_code == 200
    prompt = (resp.json() or {}).get("prompt") or ""
    m = re.search(r"(\d+)\s*\+\s*(\d+)", prompt)
    assert m
    ans = str(int(m.group(1)) + int(m.group(2)))

    # Let TTL expire
    time.sleep(1.5)

    # Verify should now fail (expired challenge)
    resp = client.post(
        "/api/auth/2fa/gate/verify/",
        data=json.dumps({"response": ans}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code in (400, 403)


@override_settings(APP_ENV="test")
def test_passphrase_required_enforcement_and_success(monkeypatch):
    """
    PASS_REQUIRED=True: initial login returns 403 generic but sets pending_2fa_user.
    After setting and verifying passphrase -> re-login issues e-OTP (risk low).
    """
    client = Client()
    headers = _csrf_headers(client)

    monkeypatch.setenv("PASS_ENABLE", "1")
    monkeypatch.setenv("PASS_REQUIRED", "1")
    # Gate disabled (focus passphrase)
    monkeypatch.setenv("GATE_ENABLE", "0")

    u, username, password = _create_superuser()

    # First login -> 403 generic (pass_required)
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 403

    # Set passphrase
    resp = client.post(
        "/api/auth/2fa/passphrase/set/",
        data=json.dumps({"passphrase": "alpha"}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("ok") is True

    # Wrong verify -> 403 + counter++
    resp = client.post(
        "/api/auth/2fa/passphrase/verify/",
        data=json.dumps({"passphrase": "wrong"}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 403

    # Check counter via debug endpoint
    resp_stats = client.get("/debug/eotp-stats")
    assert resp_stats.status_code == 200
    cnt = ((resp_stats.json() or {}).get("stats") or {}).get("counters") or {}
    assert cnt.get("eotp_passphrase_failed_total", 0) >= 1

    # Correct verify -> ok, session.pass_ok=True
    resp = client.post(
        "/api/auth/2fa/passphrase/verify/",
        data=json.dumps({"passphrase": "alpha"}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("ok") is True

    # Re-login with low risk -> should issue E-OTP (no gate)
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
        HTTP_X_RISK_OVERRIDE="0.10",
        **headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("status") == "pending_2fa"
    assert payload.get("fa_required") is True
    assert payload.get("gate_required") in (False, None)
    # Should have e-OTP metadata present (issued)
    assert "eotp_expires_in" in payload

    # Peek and finalize
    resp = client.post("/api/auth/2fa/email/_peek/", data="{}", content_type="application/json")
    assert resp.status_code == 200
    code = (resp.json() or {}).get("code")
    assert code

    resp = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": code}),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 200
    assert (resp.json() or {}).get("ok") is True
