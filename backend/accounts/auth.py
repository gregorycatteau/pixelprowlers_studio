# accounts/auth.py
# -----------------------------------------------------------------------------
# Auth JWT + cookies (refresh HttpOnly) pour PixelProwlers Studio
# - Serializer custom: ajoute username/is_staff/is_superuser/scopes dans le JWT
# - Endpoints:
#     POST /api/accounts/auth/login-cookie/    -> set cookie refresh + retourne access
#     POST /api/accounts/auth/refresh-cookie/  -> lit cookie refresh, rotate + retourne access
#     POST /api/accounts/auth/logout-cookie/   -> blacklist (si activé) + clear cookie
#     GET  /api/accounts/auth/whoami/          -> infos de l'utilisateur courant
# - En dev (DEBUG=True): CSRF relaxé pour simplifier les tests sur refresh/logout.
#   En prod: on exige X-CSRFToken == cookie "csrftoken" (double-submit cookie).
# - Cette version attrape toute exception et renvoie du JSON (plus de page HTML).
# -----------------------------------------------------------------------------
from __future__ import annotations

import logging
import os
from datetime import timedelta

from django.conf import settings
from django.middleware.csrf import get_token as get_csrf_token
from django_ratelimit.decorators import ratelimit
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from studio_core.metrics import record_auth_event

logger = logging.getLogger(__name__)


def _auth_log(
    request,
    endpoint: str,
    decision: str,
    *,
    user_id: int | None = None,
    risk_score: float | None = None,
    fa_required: bool | None = None,
) -> None:
    """
    Structured JSON logging (INFO) for auth events.
    Fields:
      - ts_utc, correlation_id, realm, endpoint, decision
      - risk_score, fa_required, user_id (if available)
    """
    try:
        meta = getattr(request, "META", {}) or {}
        cid = (meta.get("HTTP_X_REQUEST_ID") or "").strip()
        realm = getattr(settings, "REALM_NAME", None)
        ts = timezone.now().replace(microsecond=0).isoformat() + "Z"
        payload = {
            "ts_utc": ts,
            "correlation_id": cid,
            "realm": realm,
            "endpoint": endpoint,
            "decision": decision,
            "risk_score": risk_score,
            "fa_required": bool(fa_required) if fa_required is not None else None,
            "user_id": user_id if user_id is not None else None,
        }
        logger.info(json.dumps(payload))
    except Exception:
        # Never break the flow on logging issues
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Rate-limit & tarpit helpers (cache-based; per-IP/per-user keys)
# ──────────────────────────────────────────────────────────────────────────────
import time

from django.core.cache import cache


def _rate_key(prefix: str, request, user_id: int | None = None) -> str:
    ip = (
        (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR")
        or "-"
    )
    uid = str(user_id or getattr(getattr(request, "user", None), "pk", "anon"))
    return f"{prefix}:{uid}:{ip}"


def _rate_hit(prefix: str, request, user_id: int | None, window_sec: int) -> int:
    key = _rate_key(prefix, request, user_id)
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window_sec)
        n = 1
    return int(n)


def _rate_get(prefix: str, request, user_id: int | None) -> int:
    key = _rate_key(prefix, request, user_id)
    return int(cache.get(key, 0) or 0)


def _rate_exceeded(prefix: str, request, user_id: int | None, limit: int, window_sec: int) -> bool:
    n = _rate_get(prefix, request, user_id)
    return n >= limit


def _tarpit_sleep(fails: int, base_ms: int = 120, max_ms: int = 2000) -> None:
    # Exponential backoff with cap
    delay = min(max_ms, base_ms * (2 ** max(0, fails - 1)))
    time.sleep(delay / 1000.0)


# ──────────────────────────────────────────────────────────────────────────────
# JWT kid support — re-sign access token with kid header if provided
# ──────────────────────────────────────────────────────────────────────────────
import jwt as _pyjwt


def _resign_access_with_kid(access_token_str: str) -> str:
    """
    Re-sign the access token emitted by SimpleJWT to include a 'kid' header.
    - kid sourced from env JWT_KID or derived from REALM_NAME.
    - Uses SIMPLE_JWT SIGNING_KEY and ALGORITHM.
    Falls back to original token if anything goes wrong.
    """
    try:
        sj = getattr(settings, "SIMPLE_JWT", {}) or {}
        alg = sj.get("ALGORITHM", "RS256")
        key = sj.get("SIGNING_KEY") or settings.SECRET_KEY
        kid = os.getenv("JWT_KID") or f"{getattr(settings, 'REALM_NAME', 'realm')}-kid"
        # Decode without verification just to fetch payload; then re-encode with header kid.
        payload = _pyjwt.decode(access_token_str, options={"verify_signature": False})
        return _pyjwt.encode(payload, key, algorithm=alg, headers={"kid": kid})
    except Exception:
        return access_token_str


# === Full-Stack Auth Phase 2 additions (WebAuthn + TOTP + Clients login flow) ===
# Notes:
# - Endpoints are DRF-friendly and use JsonResponse to stay lightweight.
# - They avoid leaking details; errors are generic by design.
# - Cookies: refresh token can be set as HttpOnly; access token returned in body (short-lived).
# - Wiring in urls.py is required to expose these endpoints.
#
# Endpoints to wire:
#   POST /api/auth/webauthn/options/   -> api_auth_webauthn_options
#   POST /api/auth/webauthn/verify/    -> api_auth_webauthn_verify
#   POST /api/auth/login/              -> api_auth_login
#   POST /api/auth/totp/verify/        -> api_auth_totp_verify

import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST

User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
# E-OTP (Email OTP) — helpers & config
# ──────────────────────────────────────────────────────────────────────────────
import re as _re

try:
    from argon2 import PasswordHasher  # type: ignore

    _EOTP_PWH = PasswordHasher()
except Exception:
    _EOTP_PWH = None

_EOTP_TTL = int(os.getenv("EOTP_TTL_SECONDS", "300"))  # 5 minutes
_EOTP_COOLDOWN = int(os.getenv("EOTP_RESEND_COOLDOWN_SECONDS", "90"))  # resend cooldown
_EOTP_MAX_RESENDS = int(os.getenv("EOTP_MAX_RESENDS", "3"))
_EOTP_VERIFY_MAX_ATTEMPTS = int(os.getenv("EOTP_VERIFY_MAX_ATTEMPTS", "5"))
_EOTP_PEPPER = os.getenv("EOTP_PEPPER", getattr(settings, "SECRET_KEY", ""))


def _eotp_cache_key(session_key: str) -> str:
    return f"eotp:{session_key}"


def _eotp_hash(code: str) -> str:
    payload = f"{code}:{_EOTP_PEPPER}"
    if _EOTP_PWH is not None:
        try:
            return _EOTP_PWH.hash(payload)
        except Exception:
            pass
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _eotp_verify_hash(stored_hash: str, code: str) -> bool:
    payload = f"{code}:{_EOTP_PEPPER}"
    if _EOTP_PWH is not None:
        try:
            return _EOTP_PWH.verify(stored_hash, payload)
        except Exception:
            return False
    import hashlib
    import hmac

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored_hash, digest)


def _eotp_state_get(request):
    sk = request.session.session_key
    if not sk:
        return None
    return cache.get(_eotp_cache_key(sk))


def _eotp_state_set(request, state: dict, ttl: int | None = None) -> None:
    if not request.session.session_key:
        request.session.save()
    key = _eotp_cache_key(str(request.session.session_key))
    cache.set(key, state, timeout=int(ttl or _EOTP_TTL))


def _eotp_state_del(request) -> None:
    sk = request.session.session_key
    if sk:
        cache.delete(_eotp_cache_key(sk))


def _eotp_issue(request, user) -> dict:
    # Ensure session key exists
    if not request.session.session_key:
        request.session.save()
    now = int(timezone.now().timestamp())
    # Generate a uniform 6-digit code
    code = f"{secrets.randbelow(1_000_000):06d}"
    state = {
        "hash": _eotp_hash(code),
        "exp": now + _EOTP_TTL,
        "attempts": 0,
        "consumed": False,
        "resend_count": 1,
        "last_sent": now,
        "user_id": getattr(user, "pk", None),
    }
    # Test-only peek (APP_ENV=test): store plaintext code for E2E flow
    try:
        if getattr(settings, "APP_ENV", "") == "test":
            state["peek_code"] = code
    except Exception:
        pass
    _eotp_state_set(request, state, ttl=_EOTP_TTL)

    # Dev log of the OTP in non-prod or when EOTP_DEV_LOG is enabled (do not enable in prod)
    try:
        if getattr(settings, "DEBUG", False) or os.getenv("EOTP_DEV_LOG", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            logger.info(
                "eotp.dev_issued user_id=%s code=%s expires_in=%s",
                getattr(user, "pk", None),
                code,
                _EOTP_TTL,
            )
    except Exception:
        pass

    # Send email (minimal contents)
    try:
        subj = "Votre code de vérification — PixelProwlers Studio"
        msg = f"Votre code: {code}\nValable {int(_EOTP_TTL/60)} minute(s). Ne le partagez pas."
        send_mail(
            subj,
            msg,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            ["contact@pixelprowlers.io"],
            fail_silently=True,
        )
    except Exception:
        # Never break login flow on email issues
        pass

    return {"expires_in": _EOTP_TTL, "sent": True}


def _jwt_lifetimes_seconds() -> tuple[int, int]:
    """
    Returns (access_seconds, refresh_seconds) from SimpleJWT settings.
    Defaults conservatively if absent.
    """
    sj = getattr(settings, "SIMPLE_JWT", {}) or {}

    def _secs(key: str, default: timedelta) -> int:
        td = sj.get(key, default)
        try:
            return int(td.total_seconds())
        except Exception:
            return int(default.total_seconds())

    access_s = _secs("ACCESS_TOKEN_LIFETIME", timedelta(minutes=5))
    refresh_s = _secs("REFRESH_TOKEN_LIFETIME", timedelta(hours=24))
    return access_s, refresh_s


def _issue_jwt_response(request, user) -> JsonResponse:
    """
    Issues JWT pair for a given user and returns a JSON response:
    - Body: { ok: true, access: <str>, user: { id, username, is_superuser } }
    - HttpOnly cookies:
        - pp_refresh: refresh token (Secure/SameSite)
        - pp_realm: realm code (A/C/H) for SSR routing (no token exposure to JS)
    """
    from .auth import PPTokenObtainPairSerializer  # local import to avoid cycles

    try:
        ser = PPTokenObtainPairSerializer()
        token = ser.get_token(user)  # RefreshToken (carries .access)
        access = _resign_access_with_kid(str(token.access_token))
        refresh = str(token)
        access_s, refresh_s = _jwt_lifetimes_seconds()

        payload = {
            "ok": True,
            "access": access,
            "user": {
                "id": user.pk,
                "username": user.username,
                "is_superuser": bool(getattr(user, "is_superuser", False)),
            },
            "exp": int(timezone.now().timestamp()) + access_s,
        }
        resp = JsonResponse(payload, status=200)
        # Correlation header (generate if missing)
        resp["X-Correlation-ID"] = (
            request.META.get("HTTP_X_REQUEST_ID") or __import__("uuid").uuid4().hex
        )
        resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp["Pragma"] = "no-cache"
        resp["Expires"] = "0"

        # HttpOnly refresh cookie
        resp.set_cookie(
            key="__Host-pp_refresh",
            value=refresh,
            max_age=refresh_s,
            httponly=True,
            secure=True,
            samesite="Strict",
            domain=None,
            path="/",
        )

        # Realm cookie (HttpOnly) for SSR routing (A=Dojo, C=Clients, H=Laby)
        realm = getattr(settings, "REALM_NAME", "")
        realm_code = (
            "A"
            if realm == "dojo"
            else ("C" if realm == "clients" else ("H" if realm == "laby" else ""))
        )
        resp.set_cookie(
            key="__Host-pp_realm",
            value=realm_code or "C",
            max_age=refresh_s,
            httponly=True,
            secure=True,
            samesite="Strict",
            domain=None,
            path="/",
        )

        return resp
    except Exception as e:
        logger.exception("JWT issuance failed: %s", e)
        return JsonResponse({"ok": False, "error": "jwt_error"}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# WebAuthn (Admins / Dojo)
# ──────────────────────────────────────────────────────────────────────────────


@ratelimit(key="ip", rate="5/m", block=True)
@require_POST
@csrf_exempt  # En prod, préférer CSRF + mTLS (Dojo)
def api_auth_webauthn_options(request):
    """
    POST /api/auth/webauthn/options/
    Body: { "username"?: string }
    Retourne des PublicKeyCredentialRequestOptions conformes (rpId, timeout, allowCredentials).
    - Anti-rejeu: challenge stocké en session + TTL (60 s)
    - Rate-limit: 5/min par IP
    """
    # Rate-limit par IP
    if _rate_exceeded("webauthn:opts", request, None, limit=5, window_sec=60):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
    _rate_hit("webauthn:opts", request, None, window_sec=60)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    username = (body.get("username") or "").strip()
    rp_id = (request.get_host() or "").split(":")[0]
    # Délégation à allauth.mfa si disponible
    options = None
    try:
        from allauth.mfa.adapter import get_adapter  # type: ignore

        adapter = get_adapter(request)
        options = adapter.webauthn_get_options(request, username=username or None)
    except Exception:
        options = None

    if not options:
        import secrets as _secrets

        challenge = _secrets.token_urlsafe(32)
        options = {
            "publicKey": {
                "challenge": challenge,
                "rpId": rp_id,
                "timeout": 60000,
                "userVerification": "required",
                # allowCredentials peut rester vide si découverte par navigateur/identité
            }
        }
    # Stocke challenge + TTL 60s
    challenge = options.get("publicKey", {}).get("challenge")
    request.session["webauthn_challenge"] = challenge
    request.session["webauthn_challenge_ts"] = int(time.time())
    request.session["webauthn_username_hint"] = username
    request.session.modified = True

    resp = JsonResponse({"ok": True, "options": options}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@ratelimit(key="ip", rate="5/m", block=True)
@require_POST
@csrf_exempt  # En prod, exiger CSRF + mTLS (Dojo)
def api_auth_webauthn_verify(request):
    """
    POST /api/auth/webauthn/verify/
    Body: { "credential": { ... }, "username"?: string }
    Exige UV=required, vérifie origin/rpId, invalide le challenge (anti‑rejeu).
    """
    # Rate-limit
    if _rate_exceeded("webauthn:verify", request, None, limit=5, window_sec=60):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
    _rate_hit("webauthn:verify", request, None, window_sec=60)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    stored_challenge = request.session.get("webauthn_challenge")
    ts = int(request.session.get("webauthn_challenge_ts") or 0)
    if not stored_challenge or not ts:
        return JsonResponse({"ok": False, "error": "no_challenge"}, status=400)
    # TTL 60s
    if int(time.time()) - ts > 60:
        # Invalide le challenge expiré
        try:
            del request.session["webauthn_challenge"]
            del request.session["webauthn_challenge_ts"]
            request.session.modified = True
        except Exception:
            pass
        return JsonResponse({"ok": False, "error": "challenge_expired"}, status=400)

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "is_superuser", False):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    # Délègue à allauth.mfa si disponible (UV=required, rpId/origin)
    verified = False
    try:
        from allauth.mfa.adapter import get_adapter  # type: ignore

        adapter = get_adapter(request)
        verified = adapter.webauthn_verify_assertion(request, data, require_user_verification=True)
    except Exception:
        verified = False

    # Invalide le challenge (one-time)
    try:
        del request.session["webauthn_challenge"]
        del request.session["webauthn_challenge_ts"]
        request.session.modified = True
    except Exception:
        pass

    if not verified:
        fails = _rate_hit("webauthn:fails", request, user_id=user.pk, window_sec=600)
        _tarpit_sleep(fails)
        # Metrics + structured log (failure)
        record_auth_event(
            "webauthn",
            "fail",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=None,
            fa_required=False,
        )
        _auth_log(
            request,
            endpoint="webauthn",
            decision="fail",
            user_id=getattr(user, "pk", None),
            risk_score=None,
            fa_required=False,
        )
        return JsonResponse({"ok": False, "error": "assertion_invalid"}, status=401)

    # Signal "recent webauthn" pour le flux nonce
    request.session["recent_webauthn_at"] = int(timezone.now().timestamp())
    request.session.modified = True

    resp = _issue_jwt_response(request, user)
    # Metrics: WebAuthn verification OK (Dojo)
    record_auth_event(
        "webauthn",
        "ok",
        realm=getattr(settings, "REALM_NAME", None),
        risk_score=None,
        fa_required=False,
    )
    # Structured JSON log
    _auth_log(
        request,
        endpoint="webauthn",
        decision="ok",
        user_id=getattr(user, "pk", None),
        risk_score=None,
        fa_required=False,
    )
    return resp


# Console nonce flow (Admin console signed by WebAuthn)
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit


@require_GET
def api_auth_nonce(request):
    """
    GET /api/auth/nonce/
    Returns { nonce } and stores it in session for short-lived verification (TTL 60s).
    """
    import secrets as _secrets

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "is_superuser", False):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    ts = int(request.session.get("recent_webauthn_at", 0) or 0)
    if not ts:
        return JsonResponse({"ok": False, "error": "webauthn_required"}, status=401)

    nonce = _secrets.token_urlsafe(24)
    request.session["console_nonce"] = nonce
    request.session["console_nonce_ts"] = int(time.time())
    request.session.modified = True
    resp = JsonResponse({"ok": True, "nonce": nonce}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@require_POST
@csrf_exempt
def api_auth_nonce_verify(request):
    """
    POST /api/auth/nonce/verify
    Body: { "nonce": string, "assertion": {...} }
    Vérifie admin + nonce match + TTL (60s), consommation one-time.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    nonce = (data.get("nonce") or "").strip()
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "is_superuser", False):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    sess_nonce = (request.session.get("console_nonce") or "").strip()
    ts = int(request.session.get("console_nonce_ts") or 0)
    fresh = ts and (int(time.time()) - ts <= 60)
    ok = bool(nonce and sess_nonce and nonce == sess_nonce and fresh)

    # Consommer le nonce (one-time)
    try:
        for k in ("console_nonce", "console_nonce_ts"):
            if k in request.session:
                del request.session[k]
        request.session.modified = True
    except Exception:
        pass

    resp = JsonResponse({"ok": ok}, status=200 if ok else 400)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@require_POST
@csrf_exempt  # In prod, prefer CSRF-protected flows with same-site cookies
def api_auth_webauthn_options(request):
    """
    POST /api/auth/webauthn/options/
    Body: { "username"?: string }
    Returns a minimal PublicKeyCredentialRequestOptions-like shape.
    Stores challenge in session under 'webauthn_challenge'.
    """
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    username = (body.get("username") or "").strip()
    challenge = secrets.token_urlsafe(32)
    request.session["webauthn_challenge"] = challenge
    request.session["webauthn_username_hint"] = username
    request.session.modified = True

    # Minimal options; a full WebAuthn setup should include RP/allowCredentials, etc.
    opts = {
        "publicKey": {
            "challenge": challenge,
            "timeout": 60000,
            "userVerification": "required",
            # Relying Party ID defaults to host (handled by the browser)
        }
    }
    return JsonResponse({"ok": True, "options": opts}, status=200)


@require_POST
@csrf_exempt  # In prod, require CSRF + mTLS enforced by Caddy on Dojo
def api_auth_webauthn_verify(request):
    """
    POST /api/auth/webauthn/verify/
    Body (simplified): { "credential": { ... }, "username"?: string }
    For V1: checks presence of a stored challenge and an authenticated user (SSO/mTLS gateway).
    On success: issues JWT and refresh cookie.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    challenge = request.session.get("webauthn_challenge")
    if not challenge:
        return JsonResponse({"ok": False, "error": "no_challenge"}, status=400)

    # In a full implementation, verify the assertion using a WebAuthn library.
    # Here we require an authenticated admin user (mTLS + prior auth gateway).
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not getattr(user, "is_superuser", False):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    # Clear single-use challenge
    try:
        del request.session["webauthn_challenge"]
        request.session.modified = True
    except Exception:
        pass

    resp = _issue_jwt_response(request, user)
    # Metrics: TOTP verification OK
    record_auth_event(
        "totp",
        "ok",
        realm=getattr(settings, "REALM_NAME", None),
        risk_score=None,
        fa_required=require_ts_hdr,
    )
    # Structured JSON log
    _auth_log(
        request,
        endpoint="totp",
        decision="ok",
        user_id=getattr(user, "pk", None),
        risk_score=None,
        fa_required=require_ts_hdr,
    )
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# Clients — Email+Password login → pending_2fa → TOTP verify → JWT
# ──────────────────────────────────────────────────────────────────────────────

# TOTP bootstrap (pending 2FA user): returns secret and otpauth URL
from django.views.decorators.http import require_GET


@require_GET
def api_auth_totp_bootstrap(request):
    """
    GET /api/auth/totp/bootstrap/
    Returns: { secret, otpauth_url }
    Requires a valid pending_2fa_user in session.
    """
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "no_pending_2fa"}, status=400)
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    import base64
    import secrets as _secrets
    from urllib.parse import quote

    # Generate a base32 secret (RFC 3548)
    secret_b = _secrets.token_bytes(20)
    secret = base64.b32encode(secret_b).decode("utf-8").replace("=", "")
    issuer = getattr(settings, "PROJECT_NAME", "PixelProwlers")
    account = getattr(user, "email", "") or user.username or f"user-{user.pk}"

    otpauth_url = (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )

    # Save secret in session for activation step
    request.session["pending_totp_secret"] = secret
    request.session["pending_totp_issuer"] = issuer
    request.session.modified = True

    resp = JsonResponse({"ok": True, "secret": secret, "otpauth_url": otpauth_url}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@require_POST
@csrf_exempt
def api_auth_totp_activate(request):
    """
    POST /api/auth/totp/activate/
    Body: { "otp": "123456" }
    Creates a TOTP device for the pending user and returns recovery codes.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    # Adaptive Turnstile enforcement based on forward_auth signal (via headers)
    require_ts_hdr = str(request.META.get("HTTP_X_FA_REQUIRE_TURNSTILE", "")).lower() in (
        "1",
        "true",
        "yes",
    )
    ts_ok_hdr = str(request.META.get("HTTP_X_TURNSTILE_SUCCESS", "")).lower() in (
        "1",
        "true",
        "yes",
    )
    # OPS flag — enforce Turnstile strictly on OTP verify (even if gateway flag absent)
    fa_strict = os.getenv("FA_STRICT_ON_OTP", "").strip().lower() in ("1", "true", "yes", "on")
    ts_token_present = bool(
        (
            request.META.get("HTTP_CF_TURNSTILE_TOKEN")
            or request.META.get("HTTP_X_TURNSTILE_TOKEN")
            or ""
        ).strip()
    )
    strict_missing = fa_strict and not (ts_token_present or ts_ok_hdr)

    if (require_ts_hdr and not ts_ok_hdr) or strict_missing:
        resp = JsonResponse({"ok": False, "error": "turnstile_required"}, status=401)
        resp["X-Correlation-ID"] = (
            request.META.get("HTTP_X_REQUEST_ID") or __import__("uuid").uuid4().hex
        )
        return resp

    # Adaptive Turnstile checked earlier; now OTP input
    otp = (data.get("otp") or "").strip()
    # Rate-limit & cooldown per user+IP
    user_id = request.session.get("pending_2fa_user") or None
    fails_key = "totp:fails"
    if _rate_exceeded("totp:verify", request, user_id, limit=10, window_sec=300):
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
    # Cooldown based on recent fails
    recent_fails = _rate_get(fails_key, request, user_id)
    if recent_fails:
        _tarpit_sleep(recent_fails)
    if not otp:
        return JsonResponse({"ok": False, "error": "otp_required"}, status=400)

    user_id = request.session.get("pending_2fa_user")
    secret = (request.session.get("pending_totp_secret") or "").strip()
    if not user_id or not secret:
        return JsonResponse({"ok": False, "error": "no_pending_2fa"}, status=400)

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    try:
        import base64

        from django_otp.plugins.otp_totp.models import TOTPDevice  # type: ignore

        # Create device (unconfirmed), verify OTP, then confirm
        device = TOTPDevice(user=user, name="auth", confirmed=False)
        device.key = base64.b32decode(secret + ("=" * ((8 - len(secret) % 8) % 8)))
        device.save()

        if not device.verify_token(otp, tolerance=1):
            device.delete()
            return JsonResponse({"ok": False, "error": "otp_invalid"}, status=401)

        device.confirmed = True
        device.save()

        # Generate recovery codes (one-time display)
        import secrets as _secrets

        recovery_codes = [
            (_secrets.token_hex(4) + "-" + _secrets.token_hex(4)).upper() for _ in range(10)
        ]
        # Hash and store one-way (no plaintext persisted server-side)
        try:
            hashes = [_hash_recovery_code(user, code) for code in recovery_codes]
            request.session["totp_recovery_codes_hashes"] = hashes
            request.session["totp_recovery_codes_once"] = True
            request.session.modified = True
        except Exception:
            # Fallback: store nothing if hashing fails
            request.session["totp_recovery_codes_once"] = True
            request.session.modified = True

        resp = JsonResponse({"ok": True, "recovery_codes": recovery_codes}, status=200)
        resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp["Pragma"] = "no-cache"
        resp["Expires"] = "0"
        return resp

    except Exception as e:
        logger.exception("TOTP activation error: %s", e)
        return JsonResponse({"ok": False, "error": "totp_error"}, status=500)


@ratelimit(key="ip", rate="5/m", block=True)
@ratelimit(key="post:email", rate="10/h", block=True)
@require_POST
@csrf_protect
def api_auth_login(request):
    """
    POST /api/auth/login/
    Body: { "email": string, "password": string }  (ou { "username": string, "password": string })
    Returns: { status: "pending_2fa", user_hint } on valid credentials, else 401.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"status": "error", "error": "bad_json"}, status=400)

    # Accepte email OU username pour compat front
    email = (data.get("email") or data.get("username") or "").strip()
    password = data.get("password") or ""
    if not email or not password:
        return JsonResponse({"status": "error", "error": "missing_credentials"}, status=400)

    # Authenticate using AUTHENTICATION_BACKENDS (email as username if configured)
    # OPS flag — enforce Turnstile on login (require token)
    force_ts = os.getenv("FORCE_TURNSTILE_ON_LOGIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if force_ts:
        ts_tok = (
            request.META.get("HTTP_CF_TURNSTILE_TOKEN")
            or request.META.get("HTTP_X_TURNSTILE_TOKEN")
            or ""
        ).strip()
        if not ts_tok:
            resp = JsonResponse({"status": "error", "error": "turnstile_required"}, status=401)
            resp["X-Correlation-ID"] = (
                request.META.get("HTTP_X_REQUEST_ID") or __import__("uuid").uuid4().hex
            )
            return resp

    user = authenticate(request, username=email, password=password) or authenticate(
        request, email=email, password=password
    )
    if not user or not user.is_active:
        # Metrics + structured log (failure)
        record_auth_event(
            "login",
            "fail",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=None,
            fa_required=False,
        )
        _auth_log(
            request,
            endpoint="login",
            decision="fail",
            user_id=None,
            risk_score=None,
            fa_required=False,
        )
        return JsonResponse({"status": "error", "error": "invalid_credentials"}, status=401)

    # Stage 1 ok → require 2FA (superusers: E-OTP by email)
    request.session["pending_2fa_user"] = user.pk
    request.session["pending_2fa_at"] = int(timezone.now().timestamp())
    request.session.modified = True

    fa_required = bool(getattr(user, "is_superuser", False))
    eotp_meta = None
    if fa_required:
        try:
            eotp_meta = _eotp_issue(request, user)
        except Exception:
            eotp_meta = None

    hint_src = getattr(user, "username", "") or getattr(user, "email", "") or ""
    if "@" in hint_src:
        hint_src = hint_src.split("@")[0]
    user_hint = (hint_src[:2] + "…") if hint_src else ""

    payload = {"status": "pending_2fa", "user_hint": user_hint}
    if fa_required:
        payload["fa_required"] = True
        if eotp_meta and "expires_in" in eotp_meta:
            payload["eotp_expires_in"] = int(eotp_meta["expires_in"])

    resp = JsonResponse(payload, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"

    # Metrics + structured log
    fa_req_hdr = str(request.META.get("HTTP_X_FA_REQUIRE_TURNSTILE", "")).lower() in (
        "1",
        "true",
        "yes",
    )
    record_auth_event(
        "login",
        "pending_2fa",
        realm=getattr(settings, "REALM_NAME", None),
        risk_score=None,
        fa_required=fa_required or fa_req_hdr,
    )
    _auth_log(
        request,
        endpoint="login",
        decision="pending_2fa",
        user_id=getattr(getattr(request, "user", None), "pk", None),
        risk_score=None,
        fa_required=fa_required or fa_req_hdr,
    )
    return resp


@ratelimit(key="ip", rate="5/m", block=True)
@require_POST
@csrf_exempt
def api_auth_totp_verify(request):
    """
    POST /api/auth/totp/verify/
    Body: { "otp": "123456" }
    If the user has a valid TOTP device and OTP matches: issues JWT + refresh cookie,
    logs the user into session (optional), and clears the pending_2fa flag.
    """
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    otp = (data.get("otp") or "").strip()
    if not otp:
        return JsonResponse({"ok": False, "error": "otp_required"}, status=400)

    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "no_pending_2fa"}, status=400)

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    # Verify TOTP using django-otp / two-factor if available
    verified = False
    try:
        from django_otp import devices_for_user  # type: ignore

        for device in devices_for_user(user, for_verify=True):
            try:
                if device.verify_token(otp, tolerance=1):
                    verified = True
                    break
            except Exception:
                continue
    except Exception:
        # Library not available or misconfigured
        return JsonResponse({"ok": False, "error": "2fa_not_configured"}, status=400)

    if not verified:
        # Metrics + structured log (failure)
        record_auth_event(
            "totp",
            "fail",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=None,
            fa_required=require_ts_hdr,
        )
        _auth_log(
            request,
            endpoint="totp",
            decision="fail",
            user_id=getattr(user, "pk", None),
            risk_score=None,
            fa_required=require_ts_hdr,
        )
        return JsonResponse({"ok": False, "error": "otp_invalid"}, status=401)

    # Finalize: login session (optional) and clear pending
    try:
        login(request, user)
    except Exception:
        pass
    try:
        del request.session["pending_2fa_user"]
        del request.session["pending_2fa_at"]
        request.session.modified = True
    except Exception:
        pass

    resp = _issue_jwt_response(request, user)
    # Set realm cookie for Dojo (admin realm)
    resp.set_cookie(
        "__Host-pp_realm",
        "A",
        httponly=True,
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        samesite="Strict",
        path="/",
    )
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# E-OTP (Email OTP) endpoints — verify & resend
# ──────────────────────────────────────────────────────────────────────────────
@ratelimit(key="ip", rate="10/m", block=False)
@require_POST
@csrf_protect
def api_auth_eotp_verify(request):
    """
    POST /api/auth/2fa/email/verify/
    Body: { "code": "123456" }
    On success: login session + issue JWT & refresh cookie, clear pending 2FA.
    Errors are uniform (anti-enum). Strict rate-limit with Retry-After.
    """
    # Basic CSRF is enforced via decorator; rate limit per session/user
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    # Rate-limit verify attempts (per user+IP within TTL window)
    if _rate_exceeded(
        "eotp:verify", request, user_id, limit=_EOTP_VERIFY_MAX_ATTEMPTS, window_sec=_EOTP_TTL
    ):
        resp = JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
        # Provide Retry-After equal to remaining TTL
        state = _eotp_state_get(request) or {}
        remaining = max(0, int(state.get("exp", 0) - int(timezone.now().timestamp())))
        resp["Retry-After"] = str(max(30, remaining or 30))
        return resp
    _rate_hit("eotp:verify", request, user_id, window_sec=_EOTP_TTL)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    code = (data.get("code") or "").strip()
    if not code or not _re.match(r"^\d{6}$", code):
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    state = _eotp_state_get(request)
    now = int(timezone.now().timestamp())
    if (
        not state
        or state.get("consumed")
        or now > int(state.get("exp", 0))
        or int(state.get("user_id") or 0) != int(user_id)
    ):
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    # Constant-time verify (argon2 if available else sha256+pepper)
    ok = False
    try:
        ok = _eotp_verify_hash(str(state.get("hash") or ""), code)
    except Exception:
        ok = False

    if not ok:
        # bump attempts (best-effort)
        try:
            state["attempts"] = int(state.get("attempts", 0)) + 1
            _eotp_state_set(request, state, ttl=max(1, int(state.get("exp", now) - now)))
        except Exception:
            pass
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    # Success: consume and clear pending
    try:
        _eotp_state_del(request)
    except Exception:
        pass

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "invalid_code"}, status=401)

    try:
        login(request, user)
    except Exception:
        pass
    try:
        for k in ("pending_2fa_user", "pending_2fa_at"):
            if k in request.session:
                del request.session[k]
        request.session.modified = True
    except Exception:
        pass

    resp = _issue_jwt_response(request, user)
    # Realm cookie for Dojo (admin/superuser)
    resp.set_cookie(
        "__Host-pp_realm",
        "A",
        httponly=True,
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        samesite="Strict",
        path="/",
    )
    # Metrics/logs
    record_auth_event(
        "eotp",
        "ok",
        realm=getattr(settings, "REALM_NAME", None),
        risk_score=None,
        fa_required=True,
    )
    _auth_log(
        request,
        endpoint="eotp",
        decision="ok",
        user_id=int(user_id),
        risk_score=None,
        fa_required=True,
    )
    return resp


@ratelimit(key="ip", rate="5/m", block=False)
@require_POST
@csrf_protect
def api_auth_eotp_resend(request):
    """
    POST /api/auth/2fa/email/resend/
    Resend a new E-OTP with cooldown/quota. Returns 200 with a uniform body or 429 with Retry-After.
    """
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=401)

    state = _eotp_state_get(request)
    now_ts = int(timezone.now().timestamp())
    if (
        not state
        or now_ts > int(state.get("exp", 0))
        or int(state.get("user_id") or 0) != int(user_id)
    ):
        # Regenerate a new code if absent/expired but keep same TTL baseline
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return JsonResponse({"ok": False, "error": "invalid_state"}, status=401)
        meta = _eotp_issue(request, user)
        return JsonResponse(
            {
                "ok": True,
                "retry_after": _EOTP_COOLDOWN,
                "expires_in": int(meta.get("expires_in", _EOTP_TTL)),
            },
            status=200,
        )

    # Enforce cooldown & quota
    resend_count = int(state.get("resend_count", 1))
    last_sent = int(state.get("last_sent", 0))
    delta = now_ts - last_sent
    if resend_count >= _EOTP_MAX_RESENDS or delta < _EOTP_COOLDOWN:
        retry_after = max(1, _EOTP_COOLDOWN - max(0, delta))
        resp = JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
        resp["Retry-After"] = str(retry_after)
        return resp

    # Regenerate a fresh code (invalidate the previous by overwriting hash)
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=401)

    code = f"{secrets.randbelow(1_000_000):06d}"
    state["hash"] = _eotp_hash(code)
    state["last_sent"] = now_ts
    state["resend_count"] = resend_count + 1
    _eotp_state_set(request, state, ttl=max(1, int(state.get("exp", now_ts) - now_ts)))

    try:
        subj = "Votre code de vérification — PixelProwlers Studio"
        msg = f"Votre code: {code}\nValable {max(1, int((int(state.get('exp', now_ts)) - now_ts)/60))} minute(s). Ne le partagez pas."
        send_mail(
            subj,
            msg,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            ["contact@pixelprowlers.io"],
            fail_silently=True,
        )
    except Exception:
        pass

    remaining = max(0, int(state.get("exp", now_ts) - now_ts))
    return JsonResponse(
        {"ok": True, "retry_after": _EOTP_COOLDOWN, "expires_in": remaining}, status=200
    )


@require_POST
@csrf_exempt
def api_auth_eotp_peek(request):
    """
    POST /api/auth/2fa/email/_peek/  (TEST ONLY)
    Returns the current E-OTP code for E2E tests when APP_ENV=test and a pending_2fa_user is present.
    Never enabled in production.
    """
    # Guard: only in test environment
    if getattr(settings, "APP_ENV", "") != "test":
        return JsonResponse({"ok": False, "error": "not_allowed"}, status=403)

    # Require a pending_2fa_user in session
    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    state = _eotp_state_get(request) or {}
    code = state.get("peek_code")
    if not code:
        return JsonResponse({"ok": False, "error": "unavailable"}, status=404)

    return JsonResponse({"ok": True, "code": str(code)}, status=200)


def _hash_recovery_code(user, code: str) -> str:
    """
    One-way hash of a recovery code, salted with user-specific data and SECRET_KEY.
    This allows server-side verification without storing plaintext codes.
    """
    import hashlib

    payload = f"{getattr(user, 'pk', '0')}::{code}::{getattr(settings, 'SECRET_KEY', '')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@require_POST
@csrf_exempt
def api_auth_totp_recovery_export(request):
    """
    POST /api/auth/totp/recovery/export/
    Body:
      - format: "zip" | "pgp"
      - codes: string[]            (the recovery codes just shown to the user)
      - password: string           (required if format=="zip"; never stored)
      - pgp_public_key: string     (ASCII-armored; required if format=="pgp")

    Behavior:
      - Verifies provided codes against server-stored hashes (one-way).
      - If OK:
          * "zip": returns an AES-256 encrypted ZIP (requires pyzipper) containing recovery-codes.txt
          * "pgp": returns an ASCII-armored PGP message (requires pgpy) with the recovery codes
      - Never persists plaintext codes server-side.
    """
    # Identify user (prefer pending 2FA onboarding; otherwise authenticated user)
    user = getattr(request, "user", None)
    user_id = request.session.get("pending_2fa_user")
    if user_id and (not user or not getattr(user, "is_authenticated", False)):
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            user = None

    if not user or (not getattr(user, "is_authenticated", False) and not user_id):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    fmt = (body.get("format") or "").strip().lower()
    codes = body.get("codes") or []
    if not isinstance(codes, list) or not all(isinstance(x, str) and x for x in codes):
        return JsonResponse({"ok": False, "error": "codes_required"}, status=400)

    # Verify codes against stored hashes
    hashes_session = request.session.get("totp_recovery_codes_hashes") or []
    provided_hashes = [_hash_recovery_code(user, c) for c in codes]
    if set(provided_hashes) != set(hashes_session):
        return JsonResponse({"ok": False, "error": "codes_mismatch"}, status=400)

    # Prepare plaintext payload (never persisted)
    plaintext = "\n".join(codes) + "\n"

    if fmt == "zip":
        # Require strong password-protected ZIP (AES-256). Needs pyzipper.
        password = body.get("password") or ""
        if not isinstance(password, str) or len(password) < 8:
            return JsonResponse({"ok": False, "error": "weak_password"}, status=400)

        try:
            import io

            import pyzipper  # type: ignore

            buf = io.BytesIO()
            with pyzipper.AESZipFile(
                buf, "w", compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.setencryption(pyzipper.WZ_AES, nbits=256)
                zf.writestr("recovery-codes.txt", plaintext.encode("utf-8"))
            buf.seek(0)

            resp = HttpResponse(buf.getvalue(), content_type="application/zip")
            resp["Content-Disposition"] = 'attachment; filename="recovery-codes.zip"'
            # Do not cache
            resp["Cache-Control"] = "no-store"
            return resp
        except ImportError:
            return JsonResponse({"ok": False, "error": "zip_aes_not_available"}, status=501)
        except Exception:
            return JsonResponse({"ok": False, "error": "zip_error"}, status=500)

    if fmt == "pgp":
        # Encrypt with provided public key, return ASCII-armored message. Needs pgpy.
        pgp_pub = body.get("pgp_public_key") or ""
        if not isinstance(pgp_pub, str) or "BEGIN PGP PUBLIC KEY" not in pgp_pub:
            return JsonResponse({"ok": False, "error": "pgp_public_key_required"}, status=400)
        try:
            import pgpy  # type: ignore

            key, _ = pgpy.PGPKey.from_blob(pgp_pub)
            msg = pgpy.PGPMessage.new(plaintext)
            enc = key.encrypt(msg)
            armored = str(enc)

            resp = HttpResponse(armored, content_type="application/pgp-encrypted")
            resp["Content-Disposition"] = 'attachment; filename="recovery-codes.asc"'
            resp["Cache-Control"] = "no-store"
            return resp
        except ImportError:
            return JsonResponse({"ok": False, "error": "pgp_not_available"}, status=501)
        except Exception:
            return JsonResponse({"ok": False, "error": "pgp_error"}, status=500)

    return JsonResponse({"ok": False, "error": "unsupported_format"}, status=400)


@require_POST
@csrf_exempt
def api_auth_totp_revoke(request):
    """
    POST /api/auth/totp/revoke/
    Body: { "password": "..." }  (re-auth required)

    Revokes all TOTP devices for the user (or pending 2FA user).
    Clears any stored recovery code hashes (one-way) from the session.
    """
    # Identify user (prefer authenticated; fallback to pending_2fa_user during onboarding)
    user = getattr(request, "user", None)
    user_id = request.session.get("pending_2fa_user")
    if user_id and (not user or not getattr(user, "is_authenticated", False)):
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            user = None

    if not user or (not getattr(user, "is_authenticated", False) and not user_id):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    password = (data.get("password") or "").strip()
    if not password:
        return JsonResponse({"ok": False, "error": "password_required"}, status=400)

    # Re-authenticate (email or username)
    email_or_username = getattr(user, "email", "") or getattr(user, "username", "")
    if not (
        authenticate(request, username=email_or_username, password=password)
        or authenticate(request, email=email_or_username, password=password)
    ):
        return JsonResponse({"ok": False, "error": "reauth_failed"}, status=401)

    # Revoke devices
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice  # type: ignore

        TOTPDevice.objects.filter(user=user).delete()
    except Exception:
        # If OTP app missing, still clear session state; return 200 for idempotency
        pass

    # Clear any stored hashes (session-scoped, one-way)
    request.session.pop("totp_recovery_codes_hashes", None)
    request.session.pop("totp_recovery_codes_once", None)
    request.session.modified = True

    resp = JsonResponse({"ok": True, "revoked": True}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


@require_POST
@csrf_exempt
def api_auth_totp_recovery_regenerate(request):
    """
    POST /api/auth/totp/recovery/regenerate/
    Body:
      - password: string   (re-auth, never stored)

    Regenerates recovery codes (one-time display). Invalidates previous hashes.
    Stores only one-way hashes in session; never persists plaintext server-side.
    """
    # Identify user (prefer authenticated; fallback to pending_2FA)
    user = getattr(request, "user", None)
    user_id = request.session.get("pending_2fa_user")
    if user_id and (not user or not getattr(user, "is_authenticated", False)):
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            user = None

    if not user or (not getattr(user, "is_authenticated", False) and not user_id):
        return JsonResponse({"ok": False, "error": "auth_required"}, status=401)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    password = (data.get("password") or "").strip()
    if not password:
        return JsonResponse({"ok": False, "error": "password_required"}, status=400)

    # Re-authenticate (email or username)
    email_or_username = getattr(user, "email", "") or getattr(user, "username", "")
    if not (
        authenticate(request, username=email_or_username, password=password)
        or authenticate(request, email=email_or_username, password=password)
    ):
        return JsonResponse({"ok": False, "error": "reauth_failed"}, status=401)

    # Generate new codes (display once)
    import secrets as _secrets

    recovery_codes = [
        (_secrets.token_hex(4) + "-" + _secrets.token_hex(4)).upper() for _ in range(10)
    ]

    # Invalidate previous and store new hashes (one-way)
    try:
        hashes = [_hash_recovery_code(user, code) for code in recovery_codes]
        request.session["totp_recovery_codes_hashes"] = hashes
        request.session["totp_recovery_codes_once"] = True
        request.session.modified = True
    except Exception:
        return JsonResponse({"ok": False, "error": "hash_store_failed"}, status=500)

    resp = JsonResponse({"ok": True, "recovery_codes": recovery_codes}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp


# Blacklist (si app installée)
try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken  # noqa: F401

    _HAS_BLACKLIST = True
except Exception:
    _HAS_BLACKLIST = False


# =========================
# Serializer personnalisé
# =========================
class PPTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Ajoute des claims utiles dans le JWT (access & refresh)."""

    @classmethod
    def get_token(cls, user):
        """
        Retourne un RefreshToken (qui porte .access) enrichi de quelques claims.
        """
        token = super().get_token(user)

        # Claims baseline (ne rien mettre de sensible)
        token["username"] = user.get_username()
        token["is_staff"] = bool(getattr(user, "is_staff", False))
        token["is_superuser"] = bool(getattr(user, "is_superuser", False))

        # Scopes depuis AgentProfile actif (défense en profondeur)
        scopes = []
        try:
            ap = getattr(user, "agent_profile", None)
            if ap and getattr(ap, "is_active", False):
                scopes = list(ap.scopes or [])
        except Exception:
            scopes = []
        token["scopes"] = scopes
        return token

    def validate(self, attrs):
        """
        Laisse SimpleJWT faire l'auth, puis met à jour last_login si activé.
        """
        data = super().validate(attrs)
        # On laisse UPDATE_LAST_LOGIN à SimpleJWT via settings; pas d'autre logique ici.
        return data


class PPTokenObtainPairView(TokenObtainPairView):
    """Optionnel : /api/auth/token/ branché sur le serializer custom."""

    serializer_class = PPTokenObtainPairSerializer
    throttle_scope = "jwt_obtain"


# =========================
# Helpers cookies & CSRF
# =========================
REFRESH_COOKIE_NAME = getattr(settings, "PP_REFRESH_COOKIE_NAME", "pp_refresh")
REFRESH_COOKIE_PATH = getattr(settings, "PP_REFRESH_COOKIE_PATH", "/")
REFRESH_COOKIE_SECURE = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
REFRESH_COOKIE_SAMESITE = getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax"
REFRESH_COOKIE_DOMAIN = getattr(settings, "SESSION_COOKIE_DOMAIN", None)
# NOTE: SimpleJWT attend un timedelta ; on convertit en secondes pour max_age.
REFRESH_TOKEN_LIFETIME: timedelta = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


def _set_refresh_cookie(resp: Response, refresh_token: str) -> None:
    """Place le refresh token dans un cookie HttpOnly."""
    resp.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        domain=REFRESH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
        max_age=int(REFRESH_TOKEN_LIFETIME.total_seconds()),
    )


def _clear_refresh_cookie(resp: Response) -> None:
    resp.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        domain=REFRESH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
    )


def _require_csrf(request) -> bool:
    """
    En prod: exige X-CSRFToken == cookie csrftoken (double-submit).
    En dev: relax (retourne True).
    """
    if settings.DEBUG:
        return True
    header = request.META.get("HTTP_X_CSRFTOKEN")
    cookie = request.COOKIES.get("csrftoken")
    return bool(header and cookie and header == cookie)


# =========================
# Vues cookies (robustes)
# =========================
class LoginCookieView(APIView):
    """
    Authentifie l’utilisateur et:
    - set cookie refresh HttpOnly
    - retourne l'access token en JSON + quelques infos user (non sensibles)
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_obtain"

    def get(self, request, *args, **kwargs):
        """
        GET optionnel: permet de pré-déposer un csrftoken côté front (utile en prod).
        """
        try:
            resp = Response({"detail": "OK"}, status=status.HTTP_200_OK)
            csrft = get_csrf_token(request)
            resp.set_cookie(
                "csrftoken",
                csrft,
                secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
                samesite=getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax",
                domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
                path="/",
                httponly=False,
            )
            return resp
        except Exception as e:
            logger.exception("LoginCookieView.GET failed")
            return Response(
                {"detail": "login_cookie_get_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, *args, **kwargs):
        """
        POST: username/password -> JSON {access, user{...}} + cookie refresh HttpOnly.
        """
        try:
            ser = PPTokenObtainPairSerializer(data=request.data)
            ser.is_valid(raise_exception=True)

            access = ser.validated_data["access"]
            refresh = ser.validated_data["refresh"]
            user = ser.user

            payload = {
                "access": access,
                "user": {
                    "username": user.get_username(),
                    "is_staff": bool(user.is_staff),
                    "is_superuser": bool(user.is_superuser),
                },
            }
            resp = Response(payload, status=status.HTTP_200_OK)

            # Cookie refresh HttpOnly
            _set_refresh_cookie(resp, refresh)

            # Dépose/renouvelle aussi le csrftoken (utile pour refresh/logout en prod)
            try:
                csrft = get_csrf_token(request)
                resp.set_cookie(
                    "csrftoken",
                    csrft,
                    secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
                    samesite=getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax",
                    domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
                    path="/",
                    httponly=False,
                )
            except Exception:
                # non bloquant
                pass

            return resp

        except (ValidationError, AuthenticationFailed) as e:
            # Identifiants invalides → 401 JSON
            return Response(
                {"detail": "bad_credentials", "errors": getattr(e, "detail", str(e))},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.exception("LoginCookieView.POST failed")
            return Response(
                {"detail": "login_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RefreshCookieView(APIView):
    """
    Lit le refresh token depuis le cookie HttpOnly, vérifie/rotate/blacklist,
    renvoie un nouvel access token et réécrit le cookie refresh si rotation.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_refresh"

    def post(self, request, *args, **kwargs):
        try:
            if not _require_csrf(request):
                return Response({"detail": "CSRF check failed"}, status=status.HTTP_403_FORBIDDEN)

            raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
            if not raw:
                return Response(
                    {"detail": "No refresh cookie"}, status=status.HTTP_401_UNAUTHORIZED
                )

            try:
                refresh = RefreshToken(raw)
            except TokenError as e:
                return Response(
                    {"detail": f"Invalid refresh token: {e}"}, status=status.HTTP_401_UNAUTHORIZED
                )

            access = str(refresh.access_token)

            rotate = bool(settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS", False))
            blacklist_after = bool(settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION", False))
            resp = Response({"access": access}, status=status.HTTP_200_OK)

            if rotate:
                try:
                    new_refresh = refresh.rotate()
                    if blacklist_after and _HAS_BLACKLIST:
                        try:
                            refresh.blacklist()
                        except Exception:
                            pass
                    _set_refresh_cookie(resp, str(new_refresh))
                except Exception as e:
                    return Response(
                        {"detail": f"Cannot rotate: {e}"}, status=status.HTTP_400_BAD_REQUEST
                    )

            return resp

        except Exception as e:
            logger.exception("RefreshCookieView.POST failed")
            return Response(
                {"detail": "refresh_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogoutCookieView(APIView):
    """
    Invalide (blacklist si dispo) le refresh en cookie, puis le supprime.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_refresh"

    def post(self, request, *args, **kwargs):
        try:
            if not _require_csrf(request):
                return Response({"detail": "CSRF check failed"}, status=status.HTTP_403_FORBIDDEN)

            raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
            resp = Response({"detail": "logged out"}, status=status.HTTP_200_OK)

            if raw:
                try:
                    token = RefreshToken(raw)
                    if _HAS_BLACKLIST:
                        try:
                            token.blacklist()
                        except Exception:
                            pass
                except TokenError:
                    pass

            _clear_refresh_cookie(resp)
            return resp

        except Exception as e:
            logger.exception("LogoutCookieView.POST failed")
            return Response(
                {"detail": "logout_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WhoAmIView(APIView):
    """
    Retourne des infos minimales sur l'utilisateur courant (JWT access requis).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            scopes = []
            try:
                ap = getattr(user, "agent_profile", None)
                if ap and getattr(ap, "is_active", False):
                    scopes = list(ap.scopes or [])
            except Exception:
                pass

            return Response(
                {
                    "username": user.get_username(),
                    "is_staff": bool(user.is_staff),
                    "is_superuser": bool(user.is_superuser),
                    "scopes": scopes,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("WhoAmIView.GET failed")
            return Response(
                {"detail": "whoami_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
