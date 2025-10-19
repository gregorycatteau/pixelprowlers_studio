# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .mailer import send_eotp_email
from .models import EotpChallenge

# S6 observabilité
try:
    from studio_core.metrics_backend import counter_inc, histogram_observe  # type: ignore
except Exception:  # pragma: no cover

    def counter_inc(*args, **kwargs):
        return None

    def histogram_observe(*args, **kwargs):
        return None


# Optional instrumentation (PII-safe). Guarded import.
try:
    from studio_core.metrics import record_auth_event  # type: ignore
except Exception:  # pragma: no cover

    def record_auth_event(*args, **kwargs):
        return None


# -----------------------------------------------------------------------------
# Configuration (env/flags)
# -----------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    return (os.getenv(name, "").strip().lower() or ("1" if default else "0")) in (
        "1",
        "true",
        "yes",
        "on",
    )


EOTP_ENABLED = _env_bool("EOTP_ENABLED", True)
EOTP_CODE_LENGTH = _env_int("EOTP_CODE_LENGTH", 6)  # 6 or 8
EOTP_TTL = _env_int("EOTP_TTL", 300)  # seconds
EOTP_MAX_TRIES = _env_int("EOTP_MAX_TRIES", 3)
EOTP_COOLDOWN_SECONDS = _env_int("COOLDOWN_SECONDS", 30)
EOTP_STRICT_CONTEXT = _env_bool("EOTP_STRICT_CONTEXT", False)
EOTP_DISABLE_HMAC_FALLBACK = _env_bool("EOTP_DISABLE_HMAC_FALLBACK", False)

EOTP_PEPPER = os.getenv("EOTP_PEPPER", settings.SECRET_KEY)
EOTP_PEPPER_ID = os.getenv("EOTP_PEPPER_ID", "default")


# Argon2id calibration (PasswordHasher expects memory_cost in KiB)
def _parse_argon2_memory_kib(raw: str) -> int:
    s = (raw or "").strip().lower()
    if s.endswith("mib"):
        try:
            return int(s[:-3]) * 1024
        except Exception:
            return 65536
    try:
        # Accept plain numbers as MiB for convenience
        return int(s) * 1024
    except Exception:
        return 65536


ARGON2_M_KIB = _parse_argon2_memory_kib(os.getenv("ARGON2_M", "64MiB"))
ARGON2_T = _env_int("ARGON2_T", 3)
ARGON2_P = _env_int("ARGON2_P", 2)

try:
    from argon2 import PasswordHasher  # type: ignore

    _ARGON2 = PasswordHasher(time_cost=ARGON2_T, memory_cost=ARGON2_M_KIB, parallelism=ARGON2_P)
except Exception:  # pragma: no cover
    _ARGON2 = None


# -----------------------------------------------------------------------------
# Helpers (context, hashing, UA/IP canonicalisation)
# -----------------------------------------------------------------------------
def _ensure_session_key(request) -> str:
    if not getattr(request, "session", None) or not request.session.session_key:
        try:
            request.session.save()
        except Exception:
            pass
    return str(getattr(request.session, "session_key", "") or "")


def _hash_code_argon2(code: str) -> str:
    payload = f"{code}:{EOTP_PEPPER}"
    if _ARGON2 is not None:
        try:
            return _ARGON2.hash(payload)
        except Exception:
            pass
    # Fallback SHA-256
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_code_hash(stored_hash: str, code: str) -> bool:
    payload = f"{code}:{EOTP_PEPPER}"
    if _ARGON2 is not None:
        try:
            return bool(_ARGON2.verify(stored_hash, payload))
        except Exception:
            return False
    # Fallback SHA-256 (test/dev). Désactivable en production via EOTP_DISABLE_HMAC_FALLBACK=1
    if EOTP_DISABLE_HMAC_FALLBACK:
        return False
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored_hash or "", digest)


def _ua_hash(request) -> Optional[str]:
    try:
        ua = (request.META.get("HTTP_USER_AGENT") or "").strip().lower()
        if not ua:
            return None
        return hashlib.sha224(ua.encode("utf-8")).hexdigest()
    except Exception:
        return None


def _ip_prefix(request) -> Optional[str]:
    """
    PII-safe IP prefix:
    - IPv4: /24
    - IPv6: /56 (as required)
    """
    try:
        ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR")
        if not ip:
            return None
        ip_obj = ipaddress.ip_address(ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
            return f"{net.network_address}/24"
        else:
            net = ipaddress.ip_network(f"{ip}/56", strict=False)
            return f"{net.network_address}/56"
    except Exception:
        return None


def _corr_id(request) -> Optional[str]:
    try:
        return (request.META.get("HTTP_X_REQUEST_ID") or "").strip() or None
    except Exception:
        return None


def _code_space(n: int) -> int:
    n = 6 if n not in (6, 8) else n
    return 10**n


def _generate_code() -> str:
    space = _code_space(EOTP_CODE_LENGTH)
    # zero-padded to length
    return f"{secrets.randbelow(space):0{EOTP_CODE_LENGTH}d}"


@dataclass
class IssueResult:
    ok: bool
    expires_in: int
    retry_after: Optional[int] = None
    # Never return code in production; test-only retrieval via _peek endpoint.


@dataclass
class VerifyResult:
    ok: bool
    error: Optional[str] = None  # invalid_code | locked | expired | rate_limited
    retry_after: Optional[int] = None


@dataclass
class ResendResult:
    ok: bool
    retry_after: Optional[int] = None
    expires_in: Optional[int] = None


# -----------------------------------------------------------------------------
# Core services (issue / verify / resend)
# -----------------------------------------------------------------------------
@transaction.atomic
def eotp_issue(request, user=None) -> IssueResult:
    """
    Create a new challenge for the current session.
    - Invalidate previous pending for the same session (S1: we allow multi-device later; here we prefer freshness).
    - Generate 6/8 digits code, store hash Argon2id+pepper.
    - TTL = EOTP_TTL; last_sent_at=now; resend_count=1; tries_count=0.
    - Store minimal context (ua/ip prefix) + corr_id + pepper_id.
    """
    if not EOTP_ENABLED:
        return IssueResult(ok=False, expires_in=0)

    session_key = _ensure_session_key(request)
    now = timezone.now()

    # Invalidate previous pending for the same session (fresh code semantics)
    EotpChallenge.objects.filter(
        session_key=session_key, status=EotpChallenge.Status.PENDING
    ).update(status=EotpChallenge.Status.EXPIRED)

    code = _generate_code()
    ch = EotpChallenge.objects.create(
        user=getattr(user, "pk", None) and user or None,
        session_key=session_key,
        status=EotpChallenge.Status.PENDING,
        code_hash=_hash_code_argon2(code),
        algo="argon2id",
        pepper_id=EOTP_PEPPER_ID,
        tries_count=0,
        resend_count=1,
        created_at=now,
        expires_at=now + timezone.timedelta(seconds=EOTP_TTL),
        last_sent_at=now,
        context_ua=_ua_hash(request),
        context_ip_prefix=_ip_prefix(request),
        corr_id=_corr_id(request),
    )

    # Instrumentation (PII-safe)
    record_auth_event(
        "eotp",
        "issued",
        realm=getattr(settings, "REALM_NAME", None),
    )
    # S6: compteurs + histogramme (issue→ok)
    try:
        counter_inc("eotp_issue_total")
        # stocker le timestamp d'émission pour histogramme issue→ok
        cache.set(f"eotp:issue_ts:{session_key}", int(now.timestamp()), timeout=EOTP_TTL)
    except Exception:
        pass
    # S2: envoi réel via mailer (APP_ENV != test)
    try:
        if (getattr(settings, "APP_ENV", "") or "").strip().lower() != "test":
            to_email = (getattr(user, "email", "") or "").strip()
            if to_email:
                send_eotp_email(to_email, code, EOTP_TTL, _corr_id(request))
    except Exception:
        # Ne pas interrompre le flux OTP si l'envoi mail échoue
        pass

    # In tests (APP_ENV=test), we store plaintext code via accounts/_peek endpoint logic.
    try:
        if getattr(settings, "APP_ENV", "") == "test":
            # Attach to session for existing _peek endpoint if used
            request.session["eotp_peek_code"] = code
            request.session.modified = True
    except Exception:
        pass

    return IssueResult(ok=True, expires_in=EOTP_TTL)


@transaction.atomic
def eotp_verify(request, code: str) -> VerifyResult:
    """
    Verify a user-supplied code against the latest pending challenge for the session.
    - Enforce TTL, tries_count, and optional strict context (UA/IP prefix).
    - Constant-time verification via Argon2id.verify (or HMAC fallback).
    - On success: status → consumed. On reaching MAX_TRIES: status → locked.
    """
    if not EOTP_ENABLED:
        return VerifyResult(ok=False, error="invalid_code")

    session_key = _ensure_session_key(request)
    now = timezone.now()

    # Latest pending challenge for this session
    ch = (
        EotpChallenge.objects.select_for_update(skip_locked=True)
        .filter(session_key=session_key, status=EotpChallenge.Status.PENDING)
        .order_by("-created_at")
        .first()
    )
    if not ch:
        record_auth_event("eotp", "failed", realm=getattr(settings, "REALM_NAME", None))
        try:
            counter_inc("eotp_failed_total")
        except Exception:
            pass
        return VerifyResult(ok=False, error="invalid_code")

    # TTL check
    if now > ch.expires_at:
        ch.status = EotpChallenge.Status.EXPIRED
        ch.save(update_fields=["status"])
        record_auth_event("eotp", "expired", realm=getattr(settings, "REALM_NAME", None))
        try:
            counter_inc("eotp_expired_total")
        except Exception:
            pass
        return VerifyResult(ok=False, error="expired")

    # Context (optional strict policy)
    if EOTP_STRICT_CONTEXT:
        ua_ok = not ch.context_ua or ch.context_ua == _ua_hash(request)
        ip_ok = not ch.context_ip_prefix or ch.context_ip_prefix == _ip_prefix(request)
        if not (ua_ok and ip_ok):
            # Do not leak which one mismatched
            ch.tries_count = min(EOTP_MAX_TRIES, ch.tries_count + 1)
            if ch.tries_count >= EOTP_MAX_TRIES:
                ch.status = EotpChallenge.Status.LOCKED
                ch.save(update_fields=["tries_count", "status"])
                record_auth_event("eotp", "locked", realm=getattr(settings, "REALM_NAME", None))
                try:
                    counter_inc("eotp_locked_total")
                except Exception:
                    pass
                return VerifyResult(ok=False, error="locked")
            ch.save(update_fields=["tries_count"])
            record_auth_event("eotp", "failed", realm=getattr(settings, "REALM_NAME", None))
            try:
                counter_inc("eotp_failed_total")
            except Exception:
                pass
            return VerifyResult(ok=False, error="invalid_code")

    # Verify constant-time
    ok = False
    try:
        ok = _verify_code_hash(ch.code_hash or "", code or "")
    except Exception:
        ok = False

    if not ok:
        ch.tries_count = min(EOTP_MAX_TRIES, ch.tries_count + 1)
        if ch.tries_count >= EOTP_MAX_TRIES:
            ch.status = EotpChallenge.Status.LOCKED
            ch.save(update_fields=["tries_count", "status"])
            record_auth_event("eotp", "locked", realm=getattr(settings, "REALM_NAME", None))
            try:
                counter_inc("eotp_locked_total")
            except Exception:
                pass
            return VerifyResult(ok=False, error="locked")
        ch.save(update_fields=["tries_count"])
        record_auth_event("eotp", "failed", realm=getattr(settings, "REALM_NAME", None))
        try:
            counter_inc("eotp_failed_total")
        except Exception:
            pass
        return VerifyResult(ok=False, error="invalid_code")

    # Success → consume
    ch.status = EotpChallenge.Status.CONSUMED
    ch.save(update_fields=["status"])
    record_auth_event("eotp", "ok", realm=getattr(settings, "REALM_NAME", None))
    # Compteurs + histogramme issue→ok
    try:
        counter_inc("eotp_ok_total")
        issue_ts = cache.get(f"eotp:issue_ts:{session_key}")
        if isinstance(issue_ts, int):
            delta = max(0.0, timezone.now().timestamp() - float(issue_ts))
            histogram_observe("eotp_issue_to_ok_seconds", delta)
            cache.delete(f"eotp:issue_ts:{session_key}")
    except Exception:
        pass
    return VerifyResult(ok=True)


@transaction.atomic
def eotp_resend(request, user=None) -> ResendResult:
    """
    Resend a fresh code with cooldown/quota minimal (S1).
    - If cooldown active: return 429 profile via retry_after.
    - Invalidate previous pending and issue a new challenge.
    """
    if not EOTP_ENABLED:
        return ResendResult(ok=False, retry_after=EOTP_COOLDOWN_SECONDS, expires_in=None)

    session_key = _ensure_session_key(request)
    now = timezone.now()
    # S2: quota utilisateur (3/h) en plus du cooldown session
    try:
        if user is not None and getattr(user, "pk", None):
            quota_key = f"eotp:resend:user:{int(user.pk)}:h"
            try:
                count = cache.incr(quota_key)
            except Exception:
                cache.set(quota_key, 1, timeout=3600)
                count = 1
            if int(count) > 3:
                record_auth_event("eotp", "failed", realm=getattr(settings, "REALM_NAME", None))
                return ResendResult(ok=False, retry_after=60, expires_in=None)
    except Exception:
        # Ne pas casser le flux en cas de cache indisponible
        pass

    # Check latest pending for cooldown & quota
    latest = (
        EotpChallenge.objects.select_for_update(skip_locked=True)
        .filter(session_key=session_key, status=EotpChallenge.Status.PENDING)
        .order_by("-created_at")
        .first()
    )
    if latest:
        # Cooldown
        if latest.last_sent_at:
            delta = (now - latest.last_sent_at).total_seconds()
            if delta < EOTP_COOLDOWN_SECONDS:
                retry_after = max(1, int(EOTP_COOLDOWN_SECONDS - delta))
                record_auth_event("eotp", "failed", realm=getattr(settings, "REALM_NAME", None))
                try:
                    counter_inc("eotp_resend_429_total")
                except Exception:
                    pass
                return ResendResult(ok=False, retry_after=retry_after, expires_in=None)

    # Invalidate all pending to avoid reuse
    EotpChallenge.objects.filter(
        session_key=session_key, status=EotpChallenge.Status.PENDING
    ).update(status=EotpChallenge.Status.EXPIRED)

    # Fresh issue
    res = eotp_issue(request, user=user)
    record_auth_event("eotp", "resent", realm=getattr(settings, "REALM_NAME", None))
    try:
        counter_inc("eotp_issue_total")
    except Exception:
        pass
    return ResendResult(ok=res.ok, retry_after=EOTP_COOLDOWN_SECONDS, expires_in=res.expires_in)
