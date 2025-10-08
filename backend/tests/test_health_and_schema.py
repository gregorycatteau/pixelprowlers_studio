"""
Minimal pytest for health and OpenAPI schema endpoints.

These tests use the Django test client (pytest-django provides the `client` fixture)
and require DB access because a request-level audit middleware writes an AuditLog.
"""

from __future__ import annotations

import json

import pytest

# The request audit middleware writes to the DB on every response,
# so enable database access for this test module.
pytestmark = pytest.mark.django_db(transaction=True)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200

    # Parse JSON body
    try:
        data = resp.json()
    except Exception:
        data = json.loads(resp.content.decode("utf-8"))

    assert isinstance(data, dict)
    assert data.get("status") == "ok"
    # app_env is present in the current implementation (e.g., "dev")
    assert "app_env" in data

    # X-Request-ID should be injected by middleware
    # In Django >= 3.2, TestResponse exposes `headers`
    xrid = (
        resp.headers.get("X-Request-ID") if hasattr(resp, "headers") else resp.get("X-Request-ID")
    )
    assert xrid
    assert isinstance(xrid, str)
    assert len(xrid) > 0


def test_openapi_schema_available(client):
    resp = client.get("/api/schema/")
    assert resp.status_code == 200

    # Content-Type should be JSON
    content_type = (
        resp.headers.get("Content-Type")
        if hasattr(resp, "headers")
        else resp.get("Content-Type", "")
    )
    assert "json" in (content_type or "").lower()

    # Parse JSON body
    try:
        data = resp.json()
    except Exception:
        data = json.loads(resp.content.decode("utf-8"))

    # Spectacular returns an OpenAPI document with the "openapi" field
    assert isinstance(data, dict)
    assert "openapi" in data
    # Optional sanity check: basic structure
    assert "paths" in data
