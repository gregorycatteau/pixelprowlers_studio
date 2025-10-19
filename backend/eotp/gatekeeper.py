# -*- coding: utf-8 -*-
from __future__ import annotations

import hmac
import os
import random
import string
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from django.conf import settings
from django.core.cache import cache

from .limits import backoff_get_retry_after, get_ip_prefix

# S8: supervision avancée — adaptation ±10% selon risk_operational_score
try:
    from studio_core.telemetry.runtime import (  # type: ignore
        adaptive_threshold,
        get_latest_risk_score,
    )
except Exception:  # pragma: no cover

    def get_latest_risk_score(*args, **kwargs):
        return None

    def adaptive_threshold(base: float, score):
        return base


# S8: log "self-tune event" (PII-safe) via metrics registry (best effort)
try:
    from studio_core.metrics import record_auth_event  # type: ignore
except Exception:  # pragma: no cover

    def record_auth_event(*args, **kwargs):
        return None


# Flags (runtime-read for tests/ops)
def _flag_enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


GATE_ENABLE = _flag_enabled("GATE_ENABLE", "1")
GATE_RISK_THRESHOLD = _env_float("GATE_RISK_THRESHOLD", 0.75)
GATE_DIFFICULTY = os.getenv("GATE_DIFFICULTY", "adaptive").strip().lower()  # easy|medium|adaptive
GATE_CACHE_TTL = _env_int("GATE_CACHE_TTL", 60)


@dataclass
class GateChallenge:
    kind: str  # "arith" | "word"
    prompt: str
    answer: str
    ttl: int


def _cache_key(session_key: str) -> str:
    realm = getattr(settings, "REALM_NAME", None) or os.getenv("REALM_NAME", "")
    r = (realm + ":") if realm else ""
    return f"gate:{r}{session_key or '-'}"


def _now() -> int:
    return int(time.time())


def compute_risk(request) -> float:
    """
    Retourne un score de risque ∈ [0,1] basé sur quelques heuristiques simples:
      - backoff restant (si > 0 → max risk)
      - IP prefix "vide" ou suspect → risque accru
      - horaire (00:00–05:59 UTC) → léger sur-risque
      - header X-Risk-Override pour tests (si présent, borne à [0,1])
    Note: ne persiste rien; pas d'exposition côté client.
    """
    # Test override
    try:
        over = request.META.get("HTTP_X_RISK_OVERRIDE")
        if over is not None and str(over).strip() != "":
            v = float(over)
            return max(0.0, min(1.0, v))
    except Exception:
        pass

    # Backoff restant → risque maximal
    sess = getattr(request, "session", None)
    skey = str(getattr(sess, "session_key", "") or "")
    if skey:
        bof = backoff_get_retry_after(skey)
        if bof > 0:
            return 1.0

    # IP prefix signal
    ip_pref = get_ip_prefix(request)
    risk = 0.0
    if not ip_pref or ip_pref == "-":
        risk += 0.25

    # Heure UTC "nuit" → petit sur-risque
    try:
        from django.utils import timezone

        hr = timezone.now().hour
        if 0 <= hr <= 5:
            risk += 0.1
    except Exception:
        pass

    # Petite randomisation contrôlée
    risk = min(1.0, max(0.0, risk + random.uniform(0.0, 0.2)))
    return risk


def _pick_difficulty(risk: float) -> str:
    if GATE_DIFFICULTY in ("easy", "medium"):
        return GATE_DIFFICULTY
    # adaptive
    if risk >= 0.9:
        return "medium"
    if risk >= 0.75:
        return "medium"
    if risk >= 0.5:
        return "easy"
    return "easy"


def _issue_arith() -> Tuple[str, str]:
    # x+y pour easy, x*y mod small pour medium
    a, b = random.randint(2, 9), random.randint(2, 9)
    if GATE_DIFFICULTY == "medium":
        prompt = f"{a} + {b} = ?"
        answer = str(a + b)
    else:
        prompt = f"{a} + {b} = ?"
        answer = str(a + b)
    return prompt, answer


def _issue_word() -> Tuple[str, str]:
    # petit mot aléatoire (6–8 chars)
    length = random.randint(6, 8)
    letters = string.ascii_lowercase
    w = "".join(random.choice(letters) for _ in range(length))
    return f"Écrivez le mot: {w}", w


def issue_gate_challenge(session_key: str, risk: float) -> GateChallenge:
    """
    Crée et stocke un challenge simple (arithmétique ou mot) avec TTL. Remplace l'existant.
    """
    if not session_key:
        raise ValueError("session_key required")

    diff = _pick_difficulty(risk)
    # Pour simplicité: arith par défaut; on pourrait alterner selon diff
    if diff == "medium":
        prompt, answer = _issue_arith()
    else:
        prompt, answer = _issue_arith()

    # Lire le TTL dynamiquement (permet monkeypatch/setenv en tests)
    ttl = _env_int("GATE_CACHE_TTL", GATE_CACHE_TTL)
    ch = GateChallenge(kind="arith", prompt=prompt, answer=answer, ttl=ttl)
    cache.set(
        _cache_key(session_key), {"kind": ch.kind, "answer": ch.answer, "ts": _now()}, timeout=ttl
    )
    return ch


def get_adaptive_gate_threshold() -> float:
    """
    Retourne le seuil GATE_RISK_THRESHOLD adapté ±10% selon le risk_operational_score
    observé (S8). Journalise un événement 'self_tune' PII-safe.
    """
    base = float(GATE_RISK_THRESHOLD)
    score = None
    try:
        score = get_latest_risk_score()
    except Exception:
        score = None
    eff = adaptive_threshold(base, score)
    # Log best-effort (ne doit jamais casser le flux)
    try:
        record_auth_event(
            endpoint="gatekeeper",
            decision="self_tune",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=score if (score is not None) else None,
            extras={
                "base_threshold": round(base, 4),
                "effective_threshold": round(eff, 4),
            },
        )
    except Exception:
        pass
    return eff


def verify_gate_response(session_key: str, response: str) -> bool:
    """
    Vérifie la réponse fournie en constant-time, supprime le challenge à la réussite.
    """
    if not session_key:
        return False
    data = cache.get(_cache_key(session_key)) or {}
    ans = str(data.get("answer") or "")
    if not ans:
        return False
    ok = hmac.compare_digest(ans, str(response or ""))
    if ok:
        cache.delete(_cache_key(session_key))
    return ok
