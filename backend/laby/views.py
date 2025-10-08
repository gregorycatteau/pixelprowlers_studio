# -*- coding: utf-8 -*-
"""
Honeypot (Laby) — No-op views with plausible responses, canary artifacts,
JSONL chained logging, and webhook stub.

Scope
- Expose plausible endpoints for /api/projects/*, /api/agents/*, /admin/* that
  simulate success/latency but never touch real data.
- Serve 3 canary artifacts (.env, id_ed25519, notes_admin.txt) embedding DNS/URL
  tokens to detect exfiltration attempts.
- Log every request to a JSONL file with a chained hash (tamper-evident).
- Optionally POST canary events to an external webhook (e.g., n8n).

Notes
- This module is realm-agnostic but intended to be mounted under the Laby realm.
- No DB access; everything is mock/no-op with credible shapes and latencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import requests
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

# ──────────────────────────────────────────────────────────────────────────────
# Configuration via environment
# ──────────────────────────────────────────────────────────────────────────────

LABY_JSONL_PATH = os.getenv("LABY_JSONL_PATH", "/tmp/laby_events.jsonl")
LABY_CHAIN_STATE_PATH = os.getenv("LABY_CHAIN_STATE_PATH", "/tmp/laby_chain.state")
LABY_WEBHOOK_URL = os.getenv("LABY_WEBHOOK_URL", "")  # optional (n8n or similar)

LABY_DNS_TOKEN_DOMAIN = os.getenv("LABY_DNS_TOKEN_DOMAIN", "dns-cnry.invalid")
LABY_URL_TOKEN_BASE = os.getenv("LABY_URL_TOKEN_BASE", "https://cnry.invalid/t/")
LABY_REALM = "laby"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers — latency, client meta, chained JSONL logging, webhook
# ──────────────────────────────────────────────────────────────────────────────


def _sleep_jitter_ms(low_ms: int = 80, high_ms: int = 320) -> None:
    """Sleep a small, random latency window to look realistic."""
    dur = random.uniform(low_ms / 1000.0, high_ms / 1000.0)
    time.sleep(dur)


def _client_meta(request: HttpRequest) -> Dict[str, Any]:
    """Extract IP/ASN/UA and basic request info."""
    meta = request.META or {}
    xff = (meta.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    ip = xff or meta.get("REMOTE_ADDR") or ""
    asn = (meta.get("HTTP_X_ASN") or "").strip().upper() or None
    ua = (meta.get("HTTP_USER_AGENT") or "")[:256]
    return {
        "ip": ip,
        "asn": asn,
        "ua": ua,
        "method": request.method,
        "path": request.path,
        "query": (request.META.get("QUERY_STRING") or "")[:256],
    }


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path) or "."
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass


def _load_chain_head(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _save_chain_head(path: str, h: str) -> None:
    try:
        _ensure_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(h)
    except Exception:
        pass


def _compute_chain_hash(prev: str, entry_dict: Dict[str, Any]) -> str:
    """Compute sha256(prev + canonical_json(entry)) hex digest."""
    canonical = json.dumps(entry_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    m = hashlib.sha256()
    m.update((prev or "").encode("utf-8"))
    m.update(canonical.encode("utf-8"))
    return m.hexdigest()


def _append_jsonl(path: str, entry: Dict[str, Any]) -> None:
    try:
        _ensure_dir(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _log_jsonl_event(
    request: HttpRequest,
    decision: str,
    route: str,
    payload_size: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append an event to the JSONL log with a chained hash, return the record.
    """
    meta = _client_meta(request)
    base: Dict[str, Any] = {
        "ts_utc": _now_iso(),
        "realm": LABY_REALM,
        "decision": decision,
        "route": route,
        "ip": meta["ip"],
        "asn": meta["asn"],
        "ua": meta["ua"],
        "method": meta["method"],
        "payload_size": int(payload_size),
    }
    if extra:
        base.update(extra)

    # Compute chain
    prev = _load_chain_head(LABY_CHAIN_STATE_PATH)
    entry_no_chain = dict(base)
    chain_hash = _compute_chain_hash(prev, entry_no_chain)
    entry = dict(entry_no_chain)
    entry["chain_hash"] = chain_hash

    # Persist
    _append_jsonl(LABY_JSONL_PATH, entry)
    _save_chain_head(LABY_CHAIN_STATE_PATH, chain_hash)
    return entry


def _webhook_post(url: str, payload: Dict[str, Any], timeout: float = 4.0) -> None:
    if not url:
        return
    try:
        headers: Dict[str, str] = {}
        # OPS flag — enforce HMAC presence; when enabled, do not send without a secret.
        enforce = (os.getenv("LABY_WEBHOOK_HMAC_ENFORCE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        secret_raw = os.getenv("LABY_WEBHOOK_HMAC_SECRET") or ""
        secret = secret_raw.encode("utf-8") if secret_raw else b""
        if enforce and not secret:
            # Enforce HMAC signing: skip sending if we cannot sign
            return

        # Optional HMAC signature (HMAC-SHA256) to authenticate webhook payloads.
        # Headers sent when enabled:
        #   - X-Canary-Timestamp: UNIX epoch seconds (string)
        #   - X-Canary-Signature: hex(HMAC_SHA256(secret, "{ts}.{body}"))
        #   - X-Canary-Max-Skew: "300" (seconds) — receiver may enforce a 5-minute window
        if secret:
            body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            ts = str(int(time.time()))
            mac = hmac.new(
                secret, ts.encode("utf-8") + b"." + body_bytes, hashlib.sha256
            ).hexdigest()
            headers["X-Canary-Timestamp"] = ts
            headers["X-Canary-Signature"] = mac
            headers["X-Canary-Max-Skew"] = "300"

        requests.post(url, json=payload, headers=headers, timeout=timeout)
    except Exception:
        # Honeypot must be resilient; ignore webhook failures
        pass


def _record_canary_event(
    request: HttpRequest, artifact: str, token_type: str, uid: str
) -> Dict[str, Any]:
    """
    Log a canary artifact event and notify webhook.
    """
    record = _log_jsonl_event(
        request=request,
        decision="artifact_served",
        route=f"/laby/artifacts/{artifact}",
        payload_size=0,
        extra={"artifact": artifact, "token_type": token_type, "uid": uid},
    )
    _webhook_post(
        LABY_WEBHOOK_URL,
        {
            "type": "canary_access",
            "artifact": artifact,
            "token_type": token_type,
            "uid": uid,
            "ts_utc": record.get("ts_utc"),
            "ip": record.get("ip"),
            "asn": record.get("asn"),
            "realm": LABY_REALM,
            "route": record.get("route"),
        },
    )
    return record


# ──────────────────────────────────────────────────────────────────────────────
# Plausible no-op API — Projects
# ──────────────────────────────────────────────────────────────────────────────


def _fake_projects(seed: int = 42) -> Iterable[Dict[str, Any]]:
    random.seed(seed)
    owners = [101, 102, 103]
    names = ["Atlas", "Orion", "Helios", "Nyx", "Astra"]
    statuses = ["draft", "active", "archived"]
    for i in range(1, 6):
        name = random.choice(names) + f" {i}"
        slug = slugify(name)[:80]
        yield {
            "id": 1000 + i,
            "owner": random.choice(owners),
            "name": name,
            "slug": slug,
            "description": f"{name} — initiative structurante.",
            "status": random.choice(statuses),
            "metadata": {"labels": ["honeypot", "demo"], "prio": random.choice(["H", "M", "L"])},
            "created_at": "2025-01-01T10:00:00Z",
            "updated_at": "2025-01-01T10:00:00Z",
        }


@require_GET
@csrf_exempt
def api_projects_list(request: HttpRequest) -> JsonResponse:
    _sleep_jitter_ms()
    projects = list(_fake_projects())
    _log_jsonl_event(
        request=request,
        decision="ok",
        route="/api/projects/",
        payload_size=0,
        extra={"count": len(projects)},
    )
    return JsonResponse(projects, safe=False, status=200)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_projects_detail(request: HttpRequest, slug: str) -> JsonResponse:
    _sleep_jitter_ms()
    projects = list(_fake_projects())
    match = next((p for p in projects if p["slug"] == slug), None)

    if request.method == "GET":
        if not match:
            _log_jsonl_event(request, "not_found", f"/api/projects/{slug}/")
            return JsonResponse({"detail": "Not found."}, status=404)
        _log_jsonl_event(request, "ok", f"/api/projects/{slug}/")
        return JsonResponse(match, status=200)

    if request.method == "PATCH":
        # Echo back with pretend update
        payload = {}
        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            pass
        result = dict(match or {"id": 9999, "slug": slug})
        result.update({k: v for k, v in payload.items() if k in {"name", "description", "status"}})
        result["updated_at"] = _now_iso()
        _log_jsonl_event(
            request, "ok", f"/api/projects/{slug}/", payload_size=len(request.body or b"")
        )
        return JsonResponse(result, status=200)

    # DELETE — pretend success
    _log_jsonl_event(request, "ok", f"/api/projects/{slug}/", extra={"deleted": True})
    return JsonResponse({}, status=204)


@csrf_exempt
@require_http_methods(["POST"])
def api_projects_create(request: HttpRequest) -> JsonResponse:
    _sleep_jitter_ms()
    payload = {}
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        pass
    name = (payload.get("name") or "New Project")[:200]
    slug = slugify(payload.get("slug") or name)[:80]
    response = {
        "id": random.randint(2000, 3000),
        "owner": 999,
        "name": name,
        "slug": slug,
        "description": (payload.get("description") or "")[:500],
        "status": payload.get("status") or "draft",
        "metadata": payload.get("metadata") or {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _log_jsonl_event(
        request,
        "ok",
        "/api/projects/",
        payload_size=len(request.body or b""),
        extra={"created": True},
    )
    return JsonResponse(response, status=201)


# ──────────────────────────────────────────────────────────────────────────────
# Plausible no-op API — Agents
# ──────────────────────────────────────────────────────────────────────────────


def _fake_agents() -> Iterable[Dict[str, Any]]:
    data = [
        {
            "slug": "claire",
            "name": "Claire",
            "alias": "Ops Strategist",
            "model": "gpt-4o-mini",
            "temperature": 0.4,
            "description": "Planification opérationnelle et checklists.",
            "remaining_eur_today": "9.80",
            "schema_version": "2.1.0",
            "profile_version": "2.1.0",
        },
        {
            "slug": "chloe",
            "name": "Chloé",
            "alias": "Frontend Engineer",
            "model": "gpt-4o",
            "temperature": 0.2,
            "description": "Nuxt + a11y + tests.",
            "remaining_eur_today": "12.30",
            "schema_version": "2.1.0",
            "profile_version": "2.1.0",
        },
    ]
    for a in data:
        yield a


@require_GET
@csrf_exempt
def api_agents_list(request: HttpRequest) -> JsonResponse:
    _sleep_jitter_ms()
    agents = list(_fake_agents())
    _log_jsonl_event(
        request=request, decision="ok", route="/api/agents/", extra={"count": len(agents)}
    )
    return JsonResponse({"agents": agents}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def api_agents_ask(request: HttpRequest, slug: str) -> JsonResponse:
    _sleep_jitter_ms(100, 420)
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        data = {}
    message = (data.get("message") or "").strip()
    if not message:
        _log_jsonl_event(request, "bad_request", f"/api/agents/{slug}/ask")
        return JsonResponse({"ok": False, "error": "message_required"}, status=400)

    tokens_in = max(1, len(message.split()))
    output = f"[{slug}] Echo honeypot: {message}"
    tokens_out = max(1, len(output.split()))
    resp = {
        "ok": True,
        "agent": slug,
        "provider": "mock",
        "model_uri": "mock://echo",
        "output": output,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_eur": round(tokens_out / 1000.0, 4),
        "latency_ms": random.randint(90, 420),
    }
    _log_jsonl_event(
        request,
        "ok",
        f"/api/agents/{slug}/ask",
        payload_size=len(request.body or b""),
        extra={"tokens_in": tokens_in, "tokens_out": tokens_out},
    )
    return JsonResponse(resp, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# Admin honeypot (plausible login page)
# ──────────────────────────────────────────────────────────────────────────────


@csrf_exempt
@require_http_methods(["GET", "POST"])
def admin_login_honeypot(request: HttpRequest) -> HttpResponse:
    """
    A plausible admin login form that never authenticates.
    POST always "succeeds" with a generic message.
    """
    _sleep_jitter_ms()
    if request.method == "POST":
        _log_jsonl_event(
            request,
            "admin_login_attempt",
            "/admin/login/",
            payload_size=len(request.body or b""),
        )
        html = """
        <html><head><title>Admin</title></head>
        <body><p>Merci. Votre demande est en cours de traitement…</p></body></html>
        """
        return HttpResponse(html, status=200, content_type="text/html; charset=utf-8")

    _log_jsonl_event(request, "admin_login_page", "/admin/login/")
    html = """
    <html><head><title>Admin</title></head>
    <body>
      <h1>Administration</h1>
      <form method="post">
        <input type="hidden" name="csrfmiddlewaretoken" value="..." />
        <label>Username</label><input type="text" name="username" /><br/>
        <label>Password</label><input type="password" name="password" /><br/>
        <button type="submit">Sign in</button>
      </form>
    </body></html>
    """
    return HttpResponse(html, status=200, content_type="text/html; charset=utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Canary artifacts — .env, id_ed25519, notes_admin.txt
# ──────────────────────────────────────────────────────────────────────────────


def _uid() -> str:
    # 16-byte random UID, URL-safe
    return base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")


def _dns_token(uid: str) -> str:
    return f"{uid}.{LABY_DNS_TOKEN_DOMAIN}"


def _url_token(uid: str) -> str:
    base = LABY_URL_TOKEN_BASE.rstrip("/")
    return f"{base}/{uid}"


@csrf_exempt
@require_GET
def artifact_env(request: HttpRequest) -> HttpResponse:
    """
    Fake .env file with embedded DNS/URL canary tokens.
    """
    _sleep_jitter_ms()
    uid = _uid()
    dns = _dns_token(uid)
    url = _url_token(uid)
    body = (
        f"# PixelProwlers Studio — ENV (honeypot)\n"
        f"APP_ENV=prod\n"
        f"DJANGO_SETTINGS_MODULE=studio_core.settings.prod\n"
        f"SECRET_KEY=pp_{uid}\n"
        f"REDIS_HOST={dns}\n"
        f"REDIS_PASSWORD=pp_{uid[:8]}\n"
        f"DATABASE_URL=postgres://pp:{uid[:10]}@{dns}:5432/app\n"
        f"# debug link: {url}\n"
    )
    _record_canary_event(request, artifact=".env", token_type="dns/url", uid=uid)
    resp = HttpResponse(body, status=200, content_type="text/plain; charset=utf-8")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@csrf_exempt
@require_GET
def artifact_id_ed25519(request: HttpRequest) -> HttpResponse:
    """
    Fake private key with tokens in a comment.
    """
    _sleep_jitter_ms()
    uid = _uid()
    dns = _dns_token(uid)
    url = _url_token(uid)
    # Not a real key; plausible header/footer with filler
    key_lines = [
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        base64.b64encode(os.urandom(64)).decode("ascii"),
        base64.b64encode(os.urandom(64)).decode("ascii"),
        base64.b64encode(os.urandom(48)).decode("ascii"),
        "-----END OPENSSH PRIVATE KEY-----",
        f"# cnry-dns: {dns}",
        f"# cnry-url: {url}",
    ]
    body = "\n".join(key_lines) + "\n"
    _record_canary_event(request, artifact="id_ed25519", token_type="dns/url", uid=uid)
    resp = HttpResponse(body, status=200, content_type="text/plain; charset=utf-8")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@csrf_exempt
@require_GET
def artifact_notes_admin(request: HttpRequest) -> HttpResponse:
    """
    Fake admin notes with URL token.
    """
    _sleep_jitter_ms()
    uid = _uid()
    url = _url_token(uid)
    body = (
        "Notes Admin (honeypot)\n"
        "- Procédures d'accès et rotation des secrets.\n"
        "- Rapport mensuel sécurité.\n"
        f"- Lien de référence: {url}\n"
    )
    _record_canary_event(request, artifact="notes_admin.txt", token_type="url", uid=uid)
    resp = HttpResponse(body, status=200, content_type="text/plain; charset=utf-8")
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# Utilities — Simple route to prove health (honeypot)
# ──────────────────────────────────────────────────────────────────────────────


@require_GET
@csrf_exempt
def laby_health(request: HttpRequest) -> JsonResponse:
    _log_jsonl_event(request, "ok", "/laby/health")
    return JsonResponse({"status": "ok", "realm": LABY_REALM}, status=200)
