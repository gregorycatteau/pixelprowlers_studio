# backend/ai_assistants/views.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .models import AgentProfile

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
        return AgentProfile.objects.filter(is_enabled=True).get(slug=slug)
    except Exception:
        pass
    try:
        return AgentProfile.objects.filter(is_enabled=True).get(name__iexact=slug)
    except AgentProfile.DoesNotExist:
        pass
    for a in AgentProfile.objects.filter(is_enabled=True):
        if slugify(a.name) == slug:
            return a
    return None


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
    qs = AgentProfile.objects.filter(is_enabled=True).order_by("name")
    agents = [_agent_summary(a) for a in qs]
    return JsonResponse(agents, status=200, safe=False)


@require_POST
@login_required
@user_passes_test(_is_superuser)
@csrf_protect
def api_ask_agent(request: HttpRequest, slug: str) -> JsonResponse:
    """
    POST /api/agents/<slug>/ask
    Body: { "message": "..." }
    Pour l’instant → MOCK (echo).
    """
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

    t0 = time.time()
    output = f"[{agent.name}] Echo sécurisé : {message}"
    latency_ms = int((time.time() - t0) * 1000)

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
    }
    return JsonResponse(resp, status=200)


# ──────────────────────────────────────────────────────────────────────────────
# 🖥️ Console SSR legacy (template Django existant)
# ──────────────────────────────────────────────────────────────────────────────


@csrf_protect
@user_passes_test(_is_superuser)
def ask_agent_view(request: HttpRequest, agent_name: str | None = None) -> HttpResponse:
    response_text = ""
    agents_queryset = AgentProfile.objects.filter(is_enabled=True).order_by("name")
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
