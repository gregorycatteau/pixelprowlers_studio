# -*- coding: utf-8 -*-
from __future__ import annotations

import ipaddress
import os
import random
import time
from typing import Dict, Optional, Tuple

from django.conf import settings
from django.core.cache import cache

# Optional instrumentation (PII-safe). Guarded import to avoid hard deps.
try:
    from studio_core.metrics_backend import counter_inc  # type: ignore
except Exception:  # pragma: no cover

    def counter_inc(*args, **kwargs):
        return None


try:
    # Optional: django-redis connection (for future token bucket/Lua)
    from django_redis import get_redis_connection  # type: ignore

    _HAS_DJANGO_REDIS = True
except Exception:  # pragma: no cover
    _HAS_DJANGO_REDIS = False


# Flags / defaults (can be overridden by env or Django settings)
_RATELIMIT_ENABLE = bool(os.getenv("RATELIMIT_ENABLE", "1") in ("1", "true", "yes", "on"))
_RATELIMIT_TTL_VERIFY = int(os.getenv("RATELIMIT_TTL_VERIFY", "60"))
_RATELIMIT_TTL_RESEND = int(os.getenv("RATELIMIT_TTL_RESEND", "60"))
_RATELIMIT_BUCKET_VERIFY = int(os.getenv("RATELIMIT_BUCKET_VERIFY", "5"))
_RATELIMIT_BUCKET_RESEND = int(os.getenv("RATELIMIT_BUCKET_RESEND", "3"))
_RATELIMIT_JITTER_PCT = int(os.getenv("RATELIMIT_JITTER_PCT", "10"))
_RATELIMIT_REALM_SCOPE = bool(os.getenv("RATELIMIT_REALM_SCOPE", "0") in ("1", "true", "yes", "on"))

_BACKOFF_ENABLE = bool(os.getenv("BACKOFF_VERIFY_ENABLE", "1") in ("1", "true", "yes", "on"))
_BACKOFF_STEPS = tuple(
    int(s)
    for s in (os.getenv("BACKOFF_VERIFY_STEPS", "1,2,4,8").split(",") or ["1", "2", "4", "8"])
    if str(s).strip().isdigit()
) or (1, 2, 4, 8)
_BACKOFF_TTL = int(os.getenv("BACKOFF_VERIFY_KEY_TTL", "600"))


def _now() -> int:
    return int(time.time())


def _realm_prefix() -> str:
    # Read scope dynamically from env to allow test overrides
    scope_env = os.getenv("RATELIMIT_REALM_SCOPE", "0").lower()
    scoped = scope_env in ("1", "true", "yes", "on")
    if not scoped:
        return ""
    realm = getattr(settings, "REALM_NAME", None) or os.getenv("REALM_NAME", "")
    return f"{realm}:" if realm else ""


def get_ip_prefix(request) -> str:
    """
    Returns a PII-safe IP prefix as string key:
      - IPv4: /24 prefix 'a.b.c' (no full IP)
      - IPv6: simplified /56-/64 style using first 4 hextets (pii-safe enough for keys)
    Falls back to '-' if no IP available.
    """
    meta = getattr(request, "META", {}) or {}
    raw_ip = (
        (meta.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        or meta.get("REMOTE_ADDR")
        or ""
    )
    if not raw_ip:
        return "-"
    try:
        ip_obj = ipaddress.ip_address(raw_ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            parts = raw_ip.split(".")
            return ".".join(parts[:3])  # /24
        # IPv6
        hextets = raw_ip.split(":")
        # take first 4 visible hextets (pii-safe enough)
        return ":".join((hextets + ["0", "0", "0", "0"])[:4])
    except Exception:
        return "-"


def _jittered_ttl(ttl: int) -> int:
    # Read jitter pct dynamically to support monkeypatched tests
    try:
        pct = int(os.getenv("RATELIMIT_JITTER_PCT", str(_RATELIMIT_JITTER_PCT)))
    except Exception:
        pct = _RATELIMIT_JITTER_PCT
    if pct <= 0:
        return ttl
    jitter = int(ttl * pct / 100.0)
    return max(1, ttl + random.randint(-jitter, jitter))


def _window_keys(base_key: str) -> Tuple[str, str]:
    # store as two keys to compute remaining time portable across caches
    return f"{base_key}:count", f"{base_key}:ts"


def _fixed_window_check_and_consume(base_key: str, limit: int, ttl: int) -> Tuple[bool, int]:
    """
    Portable fixed-window counter using Django cache (works across backends).
    Not strictly token-bucket but acceptable as fallback with jitter to reduce sync-bursts.
    Returns (allowed, retry_after_s).
    """
    now = _now()
    k_count, k_ts = _window_keys(base_key)
    ts = cache.get(k_ts)
    ttl_j = _jittered_ttl(ttl)

    if ts is None or not isinstance(ts, int) or now - ts >= ttl:
        # Start a new window
        cache.set(k_ts, now, timeout=ttl_j)
        cache.set(k_count, 1, timeout=ttl_j)
        return True, ttl

    # within window
    try:
        cnt = int(cache.get(k_count) or 0)
    except Exception:
        cnt = 0

    if cnt >= limit:
        retry_after = max(0, (ts + ttl) - now)
        return False, retry_after

    # increment
    cache.set(k_count, cnt + 1, timeout=(ttl - (now - ts)))
    return True, ttl - (now - ts)


def _compose_key(endpoint: str, scope_name: str, scope_val: str) -> str:
    # Key pattern: ratelimit:eotp:{endpoint}:{realm?}{scope}:{val}
    realm_p = _realm_prefix()
    safe_val = (scope_val or "-").replace(" ", "_")[:128]
    return f"ratelimit:eotp:{endpoint}:{realm_p}{scope_name}:{safe_val}"


def check_and_consume(endpoint: str, scopes: Dict[str, Optional[str]]) -> Tuple[bool, int]:
    """
    Multi-grain rate-limit (IP + session + user).
    Strategy: fixed-window with jitter (fallback-friendly). Combine as AND:
      - allowed iff all scopes allow; retry_after = max(retry_after_i).
    endpoint ∈ {"verify","resend"} controls bucket & ttl.
    """
    # Read enable dynamically (tests may change via monkeypatch)
    enable = os.getenv("RATELIMIT_ENABLE", "1").lower() in ("1", "true", "yes", "on")
    if not enable:
        return True, 0

    endpoint = (endpoint or "").strip().lower()
    if endpoint not in ("verify", "resend"):
        endpoint = "verify"

    if endpoint == "verify":
        ttl = int(os.getenv("RATELIMIT_TTL_VERIFY", str(_RATELIMIT_TTL_VERIFY)))
        bucket = int(os.getenv("RATELIMIT_BUCKET_VERIFY", str(_RATELIMIT_BUCKET_VERIFY)))
    else:
        ttl = int(os.getenv("RATELIMIT_TTL_RESEND", str(_RATELIMIT_TTL_RESEND)))
        bucket = int(os.getenv("RATELIMIT_BUCKET_RESEND", str(_RATELIMIT_BUCKET_RESEND)))

    allowed_all = True
    retry_after_max = 0

    for scope_name in ("ip", "session", "user"):
        val = scopes.get(scope_name)
        if not val:
            continue
        key = _compose_key(endpoint, scope_name, str(val))
        allowed, retry_after = _fixed_window_check_and_consume(key, bucket, ttl)
        if not allowed:
            allowed_all = False
        if retry_after > retry_after_max:
            retry_after_max = retry_after

    # S6: instrumentation — compter les 429 côté verify (resend est compté côté services)
    try:
        if not allowed_all and endpoint == "verify":
            counter_inc("eotp_verify_429_total")
    except Exception:
        pass
    return allowed_all, int(retry_after_max)


# ──────────────────────────────────────────────────────────────────────────────
# Backoff (verify) — soft tarpit by returning 429 + Retry-After during backoff
# ──────────────────────────────────────────────────────────────────────────────
def _backoff_keys(session_key: str) -> Tuple[str, str]:
    # level = 0..n, until = epoch seconds when backoff ends
    realm_p = _realm_prefix()
    base = f"backoff:{realm_p}{session_key or '-'}"
    return f"{base}:level", f"{base}:until"


def backoff_get_retry_after(session_key: str) -> int:
    """
    Returns remaining backoff seconds (>0) for a session, or 0 if not in backoff.
    """
    if not _BACKOFF_ENABLE or not session_key:
        return 0
    _, k_until = _backoff_keys(session_key)
    try:
        until = int(cache.get(k_until) or 0)
    except Exception:
        until = 0
    if until <= 0:
        return 0
    now = _now()
    return max(0, until - now)


def backoff_on_failure(session_key: str) -> int:
    """
    Increments backoff level for session and sets a new backoff window.
    Returns applied delay seconds.
    """
    if not _BACKOFF_ENABLE or not session_key:
        return 0
    k_lvl, k_until = _backoff_keys(session_key)
    try:
        lvl = int(cache.get(k_lvl) or 0)
    except Exception:
        lvl = 0
    lvl = min(lvl + 1, len(_BACKOFF_STEPS))  # cap at last step
    delay = _BACKOFF_STEPS[lvl - 1] if lvl > 0 else 0
    now = _now()
    cache.set(k_lvl, lvl, timeout=_BACKOFF_TTL)
    cache.set(k_until, now + delay, timeout=_BACKOFF_TTL)
    # S6: instrumentation — backoff appliqué
    try:
        if delay > 0:
            counter_inc("eotp_backoff_applied_total")
    except Exception:
        pass
    return delay


def backoff_reset(session_key: str) -> None:
    """
    Clears backoff state for session (on success or expiration).
    """
    if not session_key:
        return
    k_lvl, k_until = _backoff_keys(session_key)
    cache.delete(k_lvl)
    cache.delete(k_until)
