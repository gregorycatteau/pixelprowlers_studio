# backend/ai_assistants/views.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, Dict, Optional

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST
from rest_framework.throttling import ScopedRateThrottle

from .models import AgentProfile
from .security import NonceError, RequestNonce, issue_chained_nonce

# ──────────────────────────────────────────────────────────────────────────────
# 🔐 GATE: constantes & anti-bruteforce
# ──────────────────────────────────────────────────────────────────────────────

GATE_SESSION_KEY = "pp_gate_ok"
GATE_WHEN_KEY = "pp_gate_ts"

ABSURD_TRIGGERS = [
    "le soleil est bleu",
    "l'ocean pacifique borde la france",
    "2 + 2 = 5",
    "la terre est plate",
    "paris est la capitale de l'italie",
]

FAIL_WINDOW_SECONDS = 15 * 60
MAX_FAILS = 6
ASK_LOGGER = logging.getLogger("ai_assistants.ask")
MAX_MESSAGE_LENGTH = 4000


class AskAgentThrottle(ScopedRateThrottle):
    scope = "ask_agent"


def _fail_key(request: HttpRequest, stage: str) -> str:
    ip = request.META.get("REMOTE_ADDR", "ip?") or "ip?"
    user = getattr(request, "user", None)
    uid = f"user:{user.pk}" if (user and user.is_authenticated) else "anon"
    return f"gate:fail:{stage}:{uid}:{ip}"


def _inc_fail(request: HttpRequest, stage: str) -> int:
    key = _fail_key(request, stage)
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, FAIL_WINDOW_SECONDS)
        n = 1
    return int(n)


def _too_many_fails(request: HttpRequest, stage: str) -> bool:
    key = _fail_key(request, stage)
    n = cache.get(key, 0)
    return int(n) >= MAX_FAILS


def _is_superuser(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


# ──────────────────────────────────────────────────────────────────────────────
# 🧩 Helpers Agents
# ──────────────────────────────────────────────────────────────────────────────


def _agent_summary(agent: AgentProfile) -> Dict[str, Any]:
    manifest = getattr(agent, "manifest_json", None) or {}
    identity = manifest.get("identity", {}) if isinstance(manifest, dict) else {}
    # Budget restant (lecture du modèle)
    try:
        remaining = agent.remaining_today()
        remaining_str = f"{remaining:.2f}"
    except Exception:
        remaining_str = ""

    return {
        "slug": agent.slug or identity.get("slug") or slugify(agent.name),
        "name": identity.get("name") or agent.name,
        "alias": identity.get("alias") or getattr(agent, "alias", ""),
        "model": getattr(agent, "model", "gpt-4o"),
        "temperature": getattr(agent, "temperature", 0.4),
        "description": (identity.get("description") or agent.description or "")[:240],
        "remaining_eur_today": remaining_str,
        "schema_version": manifest.get("schema_version", ""),
        "profile_version": manifest.get("profile_version", ""),
    }


def _get_agent_by_slug_or_name(slug: str) -> Optional[AgentProfile]:
    try:
        return AgentProfile.objects.filter(is_active=True).get(slug=slug)
    except Exception:
        pass
    try:
        return AgentProfile.objects.filter(is_active=True).get(name__iexact=slug)
    except AgentProfile.DoesNotExist:
        pass
    for a in AgentProfile.objects.filter(is_active=True):
        if slugify(a.name) == slug:
            return a
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 📦 Logs chain & Events helpers (Sprint 00)
# ──────────────────────────────────────────────────────────────────────────────


def _uuid7() -> str:
    try:
        u = getattr(uuid, "uuid7", None)
        if callable(u):
            return str(u())
    except Exception:
        pass
    return str(uuid.uuid4())


def _now_iso() -> str:
    try:
        return timezone.now().isoformat()
    except Exception:
        import datetime as _dt

        return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()


def _append_log_entry(correlation_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    key = f"logs:{correlation_id}"
    items = cache.get(key) or []
    prev_hash = items[-1].get("hash_curr") if items else ""
    payload = {"server_ts": _now_iso(), **entry}
    h = sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8") + prev_hash.encode("utf-8")
    ).hexdigest()
    item = {"hash_prev": prev_hash, "hash_curr": h, "entry": payload}
    items.append(item)
    cache.set(key, items, timeout=90 * 24 * 3600)  # keep 90 days per baseline
    return item


def _emit_event(
    correlation_id: str, base: Dict[str, Any], event_type: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    event = {
        "type": event_type,
        "events_version": "1.0.0",
        "ts": _now_iso(),
        "server_ts": _now_iso(),
        **base,
        "payload": payload,
    }
    return _append_log_entry(correlation_id, {"event": event})


# ──────────────────────────────────────────────────────────────────────────────
# 🔑 AUTH (session) — endpoints simples pour Nuxt server routes
# ──────────────────────────────────────────────────────────────────────────────


@require_POST
@csrf_exempt  # en dev: plus simple; en prod, préfère un flux CSRF ou JWT.
def api_auth_creds(request: HttpRequest) -> JsonResponse:
    """
    POST /api/auth/creds/
    Body: { "username": "...", "password": "..." }
    Retour: { ok, user: { username, is_superuser } }
    """
    if _too_many_fails(request, "login"):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        _inc_fail(request, "login")
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        _inc_fail(request, "login")
        return JsonResponse({"ok": False, "error": "missing_credentials"}, status=400)

    user = authenticate(request, username=username, password=password)
    if not user or not user.is_active:
        n = _inc_fail(request, "login")
        # réponse générique pour ne rien divulguer
        return JsonResponse({"ok": False, "error": "invalid_credentials", "fails": n}, status=401)

    login(request, user)
    # reset compteur d’échecs sur succès
    cache.delete(_fail_key(request, "login"))

    return JsonResponse(
        {"ok": True, "user": {"username": user.username, "is_superuser": bool(user.is_superuser)}},
        status=200,
    )


@require_POST
@csrf_exempt
def api_auth_logout(request: HttpRequest) -> JsonResponse:
    """POST /api/auth/logout/ → invalide la session."""
    logout(request)
    return JsonResponse({"ok": True}, status=200)


@require_GET
def api_auth_whoami(request: HttpRequest) -> JsonResponse:
    """
    GET /api/auth/whoami/
    Retourne l’état de session + flags gate (sans rien divulguer de sensible).
    """
    u = request.user
    return JsonResponse(
        {
            "authenticated": bool(u.is_authenticated),
            "username": getattr(u, "username", None) if u.is_authenticated else None,
            "is_superuser": (
                bool(getattr(u, "is_superuser", False)) if u.is_authenticated else False
            ),
            "gate": {
                "ok": bool(request.session.get(GATE_SESSION_KEY, False)),
                "ts": request.session.get(GATE_WHEN_KEY),
            },
        },
        status=200,
    )


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_auth_nonce(request: HttpRequest) -> JsonResponse:
    """
    POST /api/auth/nonce/
    Returns a short-lived nonce (TTL 60s) for chaining protected mutations.
    """
    user_id = getattr(request.user, "pk", None)
    nonce = RequestNonce.generate(user_id=user_id)
    response = JsonResponse(
        {"ok": True, "nonce": str(nonce), "expires_in": RequestNonce.ttl_seconds},
        status=200,
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    # Provide an eager follow-up nonce to avoid waterfall calls (optional)
    issue_chained_nonce(response, user_id=user_id)
    return response


@require_POST
@csrf_exempt
def api_auth_theme(request: HttpRequest) -> JsonResponse:
    """
    POST /api/auth/theme/
    Body: { "hue": <int 0-359> }
    Stores the selected hue in the session (no PII), returns { ok: true }.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    try:
        hue_raw = data.get("hue")
        hue = int(hue_raw)
    except Exception:
        return JsonResponse({"ok": False, "error": "hue_required"}, status=400)

    if not (0 <= hue <= 359):
        return JsonResponse({"ok": False, "error": "hue_out_of_range"}, status=400)

    request.session["pp_theme_hue"] = hue
    request.session.modified = True
    return JsonResponse({"ok": True}, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# 🚧 GATE — Étape 1 : absurdité flagrante
# ──────────────────────────────────────────────────────────────────────────────


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_gate_absurdity_check(request: HttpRequest) -> JsonResponse:
    """
    POST /api/gates/absurdity-check
    Body: { "text": "..." }
    Retour: { ok, score, reason, fails? }
    """
    if _too_many_fails(request, "absurd"):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        _inc_fail(request, "absurd")
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    txt = (data.get("text") or "").strip().lower()
    txt = (
        txt.replace("’", "'")
        .replace("œ", "oe")
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("ù", "u")
        .replace("ç", "c")
    )

    matched = any(trigger in txt for trigger in ABSURD_TRIGGERS)
    if not matched:
        n = _inc_fail(request, "absurd")
        return JsonResponse(
            {"ok": False, "score": 0, "reason": "no_absurd_match", "fails": n}, status=200
        )

    return JsonResponse({"ok": True, "score": 1.0, "reason": "absurd_match"}, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# 🚪 GATE — Étape 2 : rituel de phrase
# ──────────────────────────────────────────────────────────────────────────────


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_gate_challenge_init(request: HttpRequest) -> JsonResponse:
    """
    POST /api/gates/challenge-init
    Body: { "agent"?: "Claire" }
    Retour: { ok, prompt }
    """
    user = request.user
    pseudo = (user.username or "").strip()

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        data = {}

    agent_name = (data.get("agent") or "").strip() or "Claire"
    prompt = f"Bonjour {pseudo}, système en cours de préparation. Que puis-je faire pour vous aujourd’hui ?"

    request.session["pp_gate_agent"] = agent_name
    request.session.modified = True

    return JsonResponse({"ok": True, "prompt": prompt}, status=200)


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_gate_challenge_verify(request: HttpRequest) -> JsonResponse:
    """
    POST /api/gates/challenge-verify
    Body: { "response": "...", "agent"?: "Claire" }
    Si OK → flag session + timestamp.
    """
    if _too_many_fails(request, "ritual"):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)

    user = request.user
    pseudo = (user.username or "").strip()
    first = (user.first_name or "").strip() or pseudo.split("_")[0] or pseudo

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        _inc_fail(request, "ritual")
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    agent_req = (data.get("agent") or "").strip()
    agent_session = (request.session.get("pp_gate_agent") or "").strip()
    agent = agent_req or agent_session or "Claire"

    resp = (data.get("response") or "").strip()
    if not resp:
        _inc_fail(request, "ritual")
        return JsonResponse({"ok": False, "error": "response_required"}, status=400)

    def norm(s: str) -> str:
        return (
            s.lower()
            .replace("’", "'")
            .replace("œ", "oe")
            .replace("é", "e")
            .replace("è", "e")
            .replace("ê", "e")
            .replace("à", "a")
            .replace("î", "i")
            .replace("ô", "o")
            .replace("ù", "u")
            .replace("ç", "c")
            .strip()
        )

    pattern = rf"^\s*bonjour\s+{re.escape(norm(agent))}\s*,?\s*moi\s+c'?est\s+{re.escape(norm(first))}\s+et\s+on\s+se\s+tutoie\.?\s*$"
    ok = re.match(pattern, norm(resp)) is not None

    if not ok:
        n = _inc_fail(request, "ritual")
        return JsonResponse({"ok": False, "error": "bad_phrase", "fails": n}, status=200)

    request.session[GATE_SESSION_KEY] = True
    request.session[GATE_WHEN_KEY] = time.time()
    request.session.modified = True
    return JsonResponse({"ok": True}, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# 🤖 API Agents (protégée login + superuser)
# ──────────────────────────────────────────────────────────────────────────────


@require_GET
@login_required
@user_passes_test(_is_superuser)
def api_list_agents(request: HttpRequest) -> JsonResponse:
    """
    GET /api/agents/
    Renvoie un TABLEAU ([]) pour matcher le proxy Nuxt.
    """
    qs = AgentProfile.objects.filter(is_active=True).order_by("name")
    agents = [_agent_summary(a) for a in qs]
    return JsonResponse({"agents": agents}, status=200)


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_ask_agent(request: HttpRequest, slug: str) -> JsonResponse:
    """
    POST /api/agents/<slug>/ask
    Body: { "message": "..." , "thread_id"?: "...", "idempotency_key"?: "uuidv7" }
    Mock secure echo with Sprint 00 gates: throttle, nonce, idempotency, EVENTS v1 logs.
    """
    throttle = AskAgentThrottle()
    throttle_view = SimpleNamespace(throttle_scope=AskAgentThrottle.scope)
    if not throttle.allow_request(request, throttle_view):
        wait = throttle.wait()
        return JsonResponse(
            {"ok": False, "agent": slug, "error": "rate_limited", "retry_after": wait},
            status=429,
        )

    raw_nonce = request.headers.get("X-Request-Nonce") or request.META.get("HTTP_X_REQUEST_NONCE")
    try:
        RequestNonce.validate(raw_nonce, getattr(request.user, "pk", None))
    except NonceError as exc:
        return JsonResponse({"ok": False, "agent": slug, "error": exc.code}, status=400)

    # Anti-replay window (60s)
    ts_hdr = request.META.get("HTTP_X_TIMESTAMP") or ""
    try:
        ts_int = int(ts_hdr)
    except Exception:
        return JsonResponse({"ok": False, "agent": slug, "error": "bad_timestamp"}, status=400)
    now = int(time.time())
    if abs(now - ts_int) > 60:
        return JsonResponse({"ok": False, "agent": slug, "error": "timestamp_skew"}, status=401)

    agent = _get_agent_by_slug_or_name(slug)
    if not agent:
        return JsonResponse({"ok": False, "agent": slug, "error": "Agent introuvable."}, status=404)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "agent": slug, "error": "JSON invalide."}, status=400)

    message = (data.get("message") or "").strip()
    if not message:
        return JsonResponse({"ok": False, "agent": slug, "error": "Message requis."}, status=400)
    if len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse(
            {"ok": False, "agent": slug, "error": "message_too_long", "limit": MAX_MESSAGE_LENGTH},
            status=400,
        )

    # Correlation / Idempotency
    correlation_id = getattr(request, "correlation_id", None) or _uuid7()
    idem_key = getattr(request, "idempotency_key", None)
    user_id = getattr(request.user, "pk", None)
    if idem_key:
        idem_cache_key = f"idemp:ask:{user_id}:{idem_key}"
        cached_resp = cache.get(idem_cache_key)
        if cached_resp:
            return JsonResponse(cached_resp, status=200)

    # Perform mock processing
    t0 = time.time()
    output = f"[{agent.name}] Echo sécurisé : {message}"
    latency_ms = int((time.time() - t0) * 1000)

    message_hash = sha256(message.encode("utf-8")).hexdigest()
    ASK_LOGGER.info(
        "ask_agent slug=%s message_hash=%s tokens_in=%d",
        agent.slug or slugify(agent.name),
        message_hash,
        len(message.split()),
    )

    # EVENTS v1 emission (user_message + 2+ agent_stream chunks)
    base = {
        "actor": {
            "id": str(user_id) if user_id is not None else "",
            "kind": "user",
            "role": (
                "superuser"
                if getattr(request.user, "is_superuser", False)
                else ("ops" if getattr(request.user, "is_staff", False) else "agent")
            ),
            "display_name": getattr(request.user, "username", ""),
        },
        "thread_id": (data.get("thread_id") or "") or str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "trace_id": _uuid7(),
        "span_id": str(uuid.uuid4()),
    }
    _emit_event(
        correlation_id,
        base,
        "chat:user_message",
        {"message": message, "content_type": "text/plain", "tokens": len(message.split())},
    )

    # Split output into at least 2 chunks
    mid = max(1, len(output) // 2)
    chunks = [output[:mid], output[mid:]]
    for idx, chunk in enumerate(chunks):
        _emit_event(
            correlation_id,
            base,
            "chat:agent_stream",
            {
                "chunk": chunk,
                "chunk_index": idx,
                "final": idx == (len(chunks) - 1),
                "latency_ms": latency_ms,
                "model": "mock://echo",
            },
        )

    resp = {
        "ok": True,
        "agent": agent.slug or slugify(agent.name),
        "provider": "mock",
        "model_uri": "mock://echo",
        "output": output,
        "tokens_in": len(message.split()),
        "tokens_out": len(output.split()),
        "cost_eur": 0.0,
        "latency_ms": latency_ms,
        "correlation_id": correlation_id,
    }

    if idem_key:
        cache.set(idem_cache_key, resp, timeout=120)

    return JsonResponse(resp, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# 📜 Logs (RBAC read: superuser|ops)
# ──────────────────────────────────────────────────────────────────────────────


@require_GET
@login_required
@user_passes_test(
    lambda u: bool(getattr(u, "is_superuser", False) or getattr(u, "is_staff", False))
)
def api_logs_by_correlation(request: HttpRequest) -> JsonResponse:
    """
    GET /api/logs?correlation_id=...
    RBAC: superuser|ops (is_staff) only. Returns tamper-evident chain for the correlation id.
    """
    cid = (request.GET.get("correlation_id") or "").strip()
    if not cid:
        return JsonResponse({"ok": False, "error": "correlation_id_required"}, status=400)

    key = f"logs:{cid}"
    items = cache.get(key) or []

    # PII masks
    ip = (request.META.get("REMOTE_ADDR") or "").strip()

    def _mask_ip(addr: str) -> str:
        # simple /24 for IPv4 and basic masking for IPv6
        if ":" in addr:
            parts = addr.split(":")
            # keep first 3 hextets, mask the rest
            return ":".join(parts[:3] + ["*"] * max(0, len(parts) - 3)) if parts else ""
        else:
            parts = addr.split(".")
            return ".".join(parts[:3] + ["0"]) if len(parts) == 4 else ""

    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    ua_family = "unknown"
    if "chrome" in ua:
        ua_family = "chrome"
    elif "firefox" in ua:
        ua_family = "firefox"
    elif "safari" in ua and "chrome" not in ua:
        ua_family = "safari"
    elif "curl" in ua:
        ua_family = "curl"

    return JsonResponse(
        {
            "ok": True,
            "correlation_id": cid,
            "ip_mask": _mask_ip(ip),
            "ua_family": ua_family,
            "entries": items,
        },
        status=200,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 🖥️ Console SSR legacy (template Django existant)
# ──────────────────────────────────────────────────────────────────────────────


@csrf_protect
@user_passes_test(_is_superuser)
def ask_agent_view(request: HttpRequest, agent_name: str | None = None) -> HttpResponse:
    response_text = ""
    agents_queryset = AgentProfile.objects.filter(is_active=True).order_by("name")
    selected_agent_name = (agent_name or "").lower() if agent_name else None

    if request.method == "POST":
        selected_agent_name = (request.POST.get("agent") or "").strip().lower()
        message = (request.POST.get("message") or "").strip()
        if not message:
            response_text = "⚠️ Le message est vide."
        else:
            response_text = f"[{selected_agent_name}] Echo sécurisé : {message}"

    return render(
        request,
        "ai_assistants/ask_agents.html",
        {
            "response": response_text,
            "agents": agents_queryset,
            "selected_agent": selected_agent_name,
            "manifest": "Console legacy — préférer l’UI Nuxt.",
            "agent_context": "",
            "past_logs": [],
        },
    )
