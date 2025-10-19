# studio_core/views.py
from __future__ import annotations

import json
import logging
import os
import uuid

import requests
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# S9: runtime telemetry imports (best-effort fallbacks)
try:
    from studio_core.telemetry.runtime import get_latest_risk_score  # type: ignore
except Exception:  # pragma: no cover

    def get_latest_risk_score(*args, **kwargs):
        return None


try:
    from eotp.gatekeeper import get_adaptive_gate_threshold  # type: ignore
except Exception:  # pragma: no cover

    def get_adaptive_gate_threshold():
        return None


def health(request):
    """
    Endpoint de liveness très simple.
    Renvoie 200 ASAP sans toucher la DB.
    """
    return JsonResponse(
        {"status": "ok", "app_env": os.getenv("APP_ENV", "dev")},
        status=200,
    )


def ready(request):
    """
    Endpoint de readiness.
    Vérifie la connectivité DB avec un SELECT 1; renvoie 503 si KO.
    """
    ok_db = True
    err = None
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
    except Exception as e:
        ok_db = False
        err = str(e)

    payload = {
        "status": "ok" if ok_db else "degraded",
        "checks": {"db": ok_db},
        "app_env": os.getenv("APP_ENV", "dev"),
    }
    if err:
        payload["error"] = err

    return JsonResponse(payload, status=200 if ok_db else 503)


def api_ping(request):
    """
    Petit endpoint API pour tests front/back.
    - En dev, accessible sans auth (cf. REST_FRAMEWORK/AllowAny)
    - En prod, protection par IsAuthenticated (par défaut dans base.py)
    """
    return JsonResponse({"pong": True}, status=200)


@api_view(["GET"])
@permission_classes([AllowAny])
def api_hello(request):
    """
    DRF view (AllowAny) — Simple hello endpoint for Sprint 0.
    Returns greeting message with request ID if present.
    """
    request_id = request.META.get("HTTP_X_REQUEST_ID", "unknown")
    return Response(
        {
            "message": "Hello from PixelProwlers Studio API!",
            "status": "ok",
            "request_id": request_id,
            "app_env": os.getenv("APP_ENV", "dev"),
        },
        status=200,
    )


def forward_auth_verify(request):
    """
    Micro forward_auth gateway for Caddy.

    GET /_fa/verify
    Returns:
      - 200 allow
      - 302 redirect to Antichambre (Laby)
      - 401 block

    Heuristics:
      - UA headless/bot markers
      - Bad ASN/IP lists from environment
      - Optional Turnstile success header

    Env:
      - FORWARD_AUTH_BAD_ASN="AS123,AS456"
      - FORWARD_AUTH_BLOCK_IPS="1.2.3.4,5.6.7.8"
      - FORWARD_AUTH_REQUIRE_TURNSTILE=1
      - LABY_BASE_URL="https://laby.pixelprowlers.studio"
    """
    logger = logging.getLogger(__name__)
    meta = request.META or {}

    # Correlation ID (from header or generated)
    correlation_id = meta.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex

    # Extract client IP (prefer first X-Forwarded-For)
    xff = (meta.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    ip = xff or meta.get("REMOTE_ADDR") or ""

    ua = (meta.get("HTTP_USER_AGENT") or "").lower()
    asn = (meta.get("HTTP_X_ASN") or "").upper().strip()
    # Baseline Turnstile success from header (may be overridden by server check)
    ts_header_ok = str(meta.get("HTTP_X_TURNSTILE_SUCCESS", "")).lower() in ("1", "true", "yes")

    # Path & OPS flags — enforce Turnstile on specific endpoints if configured
    raw_path = (
        request.GET.get("path")
        or meta.get("HTTP_X_ORIGINAL_URI")
        or meta.get("HTTP_X_FORWARDED_URI")
        or meta.get("HTTP_X_FORWARDED_PATH")
        or meta.get("REQUEST_URI")
        or ""
    )
    path_l = str(raw_path).lower()
    is_login = "/api/auth/login" in path_l
    is_totp_verify = "/api/auth/totp/verify" in path_l

    force_ts_login = os.getenv("FORCE_TURNSTILE_ON_LOGIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    fa_strict_on_otp = os.getenv("FA_STRICT_ON_OTP", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    # Risk config and lists
    require_ts_global = os.getenv("FORWARD_AUTH_REQUIRE_TURNSTILE", "0").lower() in (
        "1",
        "true",
        "yes",
    )
    bad_asn = {
        a.strip().upper()
        for a in (os.getenv("FORWARD_AUTH_BAD_ASN", "") or "").split(",")
        if a.strip()
    }
    block_ips = {
        a.strip() for a in (os.getenv("FORWARD_AUTH_BLOCK_IPS", "") or "").split(",") if a.strip()
    }
    laby_url = os.getenv("LABY_BASE_URL", "https://laby.pixelprowlers.studio")

    # 1) Hard block by IP
    if ip and ip in block_ips:
        record = {
            "type": "forward_auth",
            "decision": "block",
            "reasons": ["ip_blocked"],
            "risk_score": 100,
            "correlation_id": correlation_id,
            "ip": ip,
            "asn": asn or None,
            "ua_head": ua[:64],
        }
        logger.warning(json.dumps(record))
        return JsonResponse({"ok": False, "error": "blocked"}, status=401)

    # 2) Headless/bot UA
    headless_markers = (
        "headless",
        "puppeteer",
        "playwright",
        "phantomjs",
        "curl",
        "wget",
        "python-requests",
    )
    ua_risky = any(m in ua for m in headless_markers)

    # 3) Bad ASN
    asn_risky = bool(asn and asn in bad_asn)

    # 4) OTP failures (signal via header from app)
    try:
        otp_fails = int(meta.get("HTTP_X_OTP_FAILS", "0"))
    except Exception:
        otp_fails = 0
    otp_risky = otp_fails >= int(os.getenv("FORWARD_AUTH_OTP_FAILS_THRESHOLD", "3"))

    # 5) Server-side Turnstile verification (if token + secret present)
    ts_token = (
        meta.get("HTTP_CF_TURNSTILE_TOKEN")
        or meta.get("HTTP_X_TURNSTILE_TOKEN")
        or request.GET.get("turnstile_token")
    )
    ts_ok = ts_header_ok
    ts_reason = None
    ts_secret = os.getenv("TURNSTILE_SECRET") or ""
    if ts_token and ts_secret:
        try:
            resp = requests.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": ts_secret, "response": ts_token, "remoteip": ip},
                timeout=4,
            )
            data = resp.json() if resp.ok else {}
            ts_ok = bool(data.get("success"))
            ts_reason = "turnstile_ok" if ts_ok else "turnstile_fail"
        except Exception:
            ts_ok = False
            ts_reason = "turnstile_error"
    elif require_ts_global:
        ts_ok = False
        ts_reason = "turnstile_missing"

    # Risk aggregation
    reasons = []
    risk_score = 0
    if ua_risky:
        reasons.append("ua_headless")
        risk_score += 40
    if asn_risky:
        reasons.append("asn_bad")
        risk_score += 40
    if otp_risky:
        reasons.append("otp_failures")
        risk_score += min(30, otp_fails * 5)
    if ts_reason:
        reasons.append(ts_reason)
        if ts_reason != "turnstile_ok":
            risk_score += 30

    # Adaptive Turnstile requirement signal (for downstream OTP verify, etc.)
    # Enforce by OPS flags for specific paths
    if force_ts_login and is_login:
        reasons.append("force_ts_login")
    if fa_strict_on_otp and is_totp_verify:
        reasons.append("fa_strict_on_otp")

    require_turnstile = (
        require_ts_global
        or (risk_score >= int(os.getenv("FORWARD_AUTH_TURNSTILE_THRESHOLD", "40")))
        or (force_ts_login and is_login)
        or (fa_strict_on_otp and is_totp_verify)
    )

    # Decision thresholds
    redirect_threshold = int(os.getenv("FORWARD_AUTH_REDIRECT_THRESHOLD", "80"))

    if risk_score >= redirect_threshold:
        decision = "redirect_laby"
        record = {
            "type": "forward_auth",
            "decision": decision,
            "reasons": reasons,
            "risk_score": risk_score,
            "correlation_id": correlation_id,
            "ip": ip,
            "asn": asn or None,
            "ua_head": ua[:64],
        }
        logger.warning(json.dumps(record))
        resp = JsonResponse({"ok": False, "redirect": laby_url}, status=302)
        resp["Location"] = laby_url
        resp["X-FA-Require-Turnstile"] = "1" if require_turnstile else "0"
        resp["X-Correlation-ID"] = correlation_id
        return resp

    # Allow with adaptive Turnstile flag for app usage
    decision = "allow"
    record = {
        "type": "forward_auth",
        "decision": decision,
        "reasons": reasons,
        "risk_score": risk_score,
        "correlation_id": correlation_id,
        "ip": ip,
        "asn": asn or None,
        "ua_head": ua[:64],
    }
    logger.info(json.dumps(record))
    resp = JsonResponse({"ok": True, "require_turnstile": require_turnstile}, status=200)
    resp["X-FA-Require-Turnstile"] = "1" if require_turnstile else "0"
    resp["X-Correlation-ID"] = correlation_id
    return resp


def jwks_json(request):
    """
    GET /.well-known/jwks.json
    Expose the JWK Set for the current realm (RS256 only).
    - Reads SIMPLE_JWT.VERIFYING_KEY or JWT_PUBLIC_KEY (PEM)
    - Adds 'kid' from env JWT_KID or derived from REALM_NAME
    - Supports extra public keys via env JWKS_EXTRA_PUBLIC_KEYS (JSON array of PEM strings
      or objects { "pem": "...", "kid": "..." })
    - Returns {"keys": [...]} with minimal RSA fields (n,e)
    """
    sj = getattr(settings, "SIMPLE_JWT", {}) or {}
    alg = sj.get("ALGORITHM", "HS256")
    public_pem = sj.get("VERIFYING_KEY") or os.getenv("JWT_PUBLIC_KEY", "")
    default_kid = os.getenv("JWT_KID") or f"{getattr(settings, 'REALM_NAME', 'realm')}-kid"

    def _b64u_uint(val: int) -> str:
        import base64

        b = val.to_bytes((val.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

    def _make_jwk_from_pem(pem: str, kid_val: str) -> dict | None:
        try:
            # Derive RSA modulus/exponent from PEM using cryptography (if available)
            from cryptography.hazmat.backends import default_backend  # type: ignore
            from cryptography.hazmat.primitives import serialization  # type: ignore

            pub = serialization.load_pem_public_key(pem.encode("utf-8"), backend=default_backend())
            numbers = pub.public_numbers()
            return {
                "kty": "RSA",
                "use": "sig",
                "alg": alg,
                "kid": kid_val,
                "n": _b64u_uint(numbers.n),
                "e": _b64u_uint(numbers.e),
            }
        except Exception:
            return None

    keys: list[dict] = []

    # Primary (realm) key
    if alg.startswith("RS") and public_pem:
        jwk = _make_jwk_from_pem(public_pem, default_kid)
        if jwk:
            keys.append(jwk)

    # Extra public keys via env JWKS_EXTRA_PUBLIC_KEYS (JSON array)
    extra_raw = os.getenv("JWKS_EXTRA_PUBLIC_KEYS", "").strip()
    if extra_raw:
        try:
            arr = json.loads(extra_raw)
            if isinstance(arr, list):
                idx = 0
                for item in arr:
                    pem = ""
                    kid_val: str | None = None
                    if isinstance(item, str):
                        pem = item
                    elif isinstance(item, dict):
                        pem = (item.get("pem") or item.get("public_pem") or "").strip()
                        kid_val = (item.get("kid") or "").strip() or None
                    else:
                        continue
                    if not pem:
                        continue
                    if not kid_val:
                        kid_val = f"{getattr(settings, 'REALM_NAME', 'realm')}-extra-{idx}"
                    jwk_ex = _make_jwk_from_pem(pem, kid_val)
                    if jwk_ex:
                        keys.append(jwk_ex)
                        idx += 1
        except Exception:
            # Ignore malformed JWKS_EXTRA_PUBLIC_KEYS
            pass

    return JsonResponse({"keys": keys}, status=200)


@require_GET
def debug_eotp_stats(request):
    """
    GET /debug/eotp-stats (DEV/TEST uniquement)
    Retourne un snapshot JSON des compteurs internes (metrics_adapter).
    - Jamais activé en prod (gate via APP_ENV).
    Réponse:
      200: { ok: true, stats: { ts, counters:{...}, histograms:{...} } }
      404: { ok: false, error: "not_allowed" } si environnement non autorisé
      501: { ok: false, error: "adapter_unavailable" } si adapter manquant
    """
    import os as _os

    from django.conf import settings

    env = getattr(settings, "APP_ENV", None) or _os.getenv("APP_ENV", "dev")
    if str(env).lower() not in ("dev", "test"):
        return JsonResponse({"ok": False, "error": "not_allowed"}, status=404)

    try:
        from .metrics_backend import get_snapshot
    except Exception:
        return JsonResponse({"ok": False, "error": "adapter_unavailable"}, status=501)

    snap = get_snapshot()

    # S9: expose runtime intelligence (DEV/TEST only)
    try:
        ros = get_latest_risk_score()
    except Exception:
        ros = None
    try:
        agt = get_adaptive_gate_threshold()
    except Exception:
        agt = None

    return JsonResponse(
        {
            "ok": True,
            "stats": snap,
            "risk_operational_score": ros,
            "adaptive_gate_threshold": agt,
        },
        status=200,
    )
