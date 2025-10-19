# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Optional, Tuple

from django.conf import settings

# Optional metrics registry (PII-safe)
try:
    from studio_core.metrics import REGISTRY, record_auth_event  # type: ignore
except Exception:  # pragma: no cover
    REGISTRY = None

    def record_auth_event(*args, **kwargs):
        return None


# -----------------------------------------------------------------------------
# Config / Flags (S2)
# -----------------------------------------------------------------------------
MAILER_PROVIDER = (
    (os.getenv("MAILER_PROVIDER", "") or "").strip().lower()
)  # "postmark" | "smtp" | "disabled"
POSTMARK_API_TOKEN = os.getenv("POSTMARK_API_TOKEN", "").strip()
POSTMARK_FROM = (
    os.getenv("POSTMARK_FROM", os.getenv("MAIL_FROM", "")).strip() or "security@pixelprowlers.io"
)
POSTMARK_WEBHOOK_SECRET = os.getenv("POSTMARK_WEBHOOK_SECRET", "").strip()

# SMTP fallback uses Django Email settings (EMAIL_BACKEND, EMAIL_HOST, etc.)
# Fail fermé si pas de STARTTLS: à appliquer via settings prod.


def _counter(name: str, help: str, labels: Optional[dict] = None, inc: float = 1.0) -> None:
    if REGISTRY is None:
        return
    try:
        c = REGISTRY.counter(name, help, label_names=tuple(sorted((labels or {}).keys())))
        if labels:
            c.inc(labels, value=inc)
        else:
            c.inc(value=inc)
    except Exception:
        pass


def _hash_email(email: str) -> str:
    try:
        return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()
    except Exception:
        return ""


def _email_domain(email: str) -> Optional[str]:
    try:
        parts = (email or "").split("@")
        return parts[1].strip().lower() if len(parts) == 2 else None
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Postmark transport
# -----------------------------------------------------------------------------
POSTMARK_ENDPOINT = "https://api.postmarkapp.com/email"


def _postmark_request(payload: dict, token: str) -> Tuple[int, str]:
    """
    Effectue l'appel HTTP Postmark. Séparé pour faciliter le monkeypatch en tests.
    Retourne (status_code, body_text).
    """
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": token,
    }
    # Utiliser requests si dispo, sinon urllib
    try:
        import requests  # type: ignore

        resp = requests.post(POSTMARK_ENDPOINT, data=data, headers=headers, timeout=5)
        return int(resp.status_code), (resp.text or "")
    except Exception:
        try:
            from urllib.request import Request, urlopen  # type: ignore

            req = Request(POSTMARK_ENDPOINT, data=data, headers=headers, method="POST")
            with urlopen(req, timeout=5) as resp:  # nosec B310 (external call intended)
                status = getattr(resp, "status", 200)
                body = resp.read().decode("utf-8")
                return int(status), body
        except Exception as e:  # pragma: no cover
            return 0, str(e)


def _send_via_postmark(to_email: str, subject: str, text_body: str, corr_id: Optional[str]) -> bool:
    if not POSTMARK_API_TOKEN:
        return False
    payload = {
        "From": POSTMARK_FROM,
        "To": to_email,
        "Subject": subject,
        "TextBody": text_body,
        "MessageStream": "outbound",
        "Metadata": {"corr_id": corr_id or ""},
    }
    status, _ = _postmark_request(payload, POSTMARK_API_TOKEN)
    return 200 <= status < 300


# -----------------------------------------------------------------------------
# SMTP fallback (Django Email)
# -----------------------------------------------------------------------------
def _send_via_smtp(to_email: str, subject: str, text_body: str) -> bool:
    try:
        from django.core.mail import send_mail  # type: ignore

        sent = send_mail(
            subject=subject,
            message=text_body,
            from_email=POSTMARK_FROM,
            recipient_list=[to_email],
            fail_silently=False,
        )
        return bool(sent)
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def send_eotp_email(
    to_email: Optional[str], code: str, ttl_seconds: int, corr_id: Optional[str] = None
) -> bool:
    """
    Envoi d'un e‑mail e‑OTP en S2:
    - En APP_ENV=test: ne pas envoyer (tests utilisent _peek).
    - En prod/stage/dev: privilégier Postmark si MAILER_PROVIDER=postmark et token présent,
      sinon fallback SMTP si MAILER_PROVIDER=smtp.
    - PII-safe: ne loggue jamais le code; textBody minimal.
    - Incrémente des compteurs eotp_mail_send_total / mail_provider_errors_total / mail_fallback_uses_total.
    Retourne True si envoyé, False sinon.
    """
    app_env = (getattr(settings, "APP_ENV", "") or "").strip().lower()
    if app_env == "test":
        return True  # tests E2E utilisent _peek; pas d'envoi réel

    if not to_email:
        _counter("eotp_mail_provider_errors_total", "Erreurs provider mail (adresse absente)")
        return False

    subject = "Votre code de vérification — PixelProwlers"
    text_body = f"Votre code de vérification: {code}\nValide {int(ttl_seconds/60)} minute(s). Ne le partagez jamais."

    provider = MAILER_PROVIDER or ("postmark" if POSTMARK_API_TOKEN else "smtp")

    ok = False
    if provider == "postmark" and POSTMARK_API_TOKEN:
        ok = _send_via_postmark(to_email, subject, text_body, corr_id)
        if not ok:
            _counter("eotp_mail_provider_errors_total", "Erreurs provider mail (Postmark)")
            # Fallback SMTP si Postmark échoue
            fallback_ok = _send_via_smtp(to_email, subject, text_body)
            if fallback_ok:
                _counter("eotp_mail_fallback_uses_total", "Utilisations du fallback SMTP")
                ok = True

    elif provider == "smtp":
        ok = _send_via_smtp(to_email, subject, text_body)
        _counter("eotp_mail_fallback_uses_total", "Utilisations du fallback SMTP")

        if not ok:
            _counter("eotp_mail_provider_errors_total", "Erreurs provider mail (SMTP)")

    else:
        # Désactivé
        _counter("eotp_mail_provider_errors_total", "Erreurs provider mail (désactivé)")
        ok = False

    if ok:
        dom = _email_domain(to_email) or ""
        _counter("eotp_mail_send_total", "E‑OTP emails envoyés", labels={"domain": dom})
        record_auth_event(
            "mail",
            "sent",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=None,
            fa_required=True,
        )
    return ok


# -----------------------------------------------------------------------------
# Webhook Postmark — signature vérifiée
# -----------------------------------------------------------------------------
def verify_postmark_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Vérifie la signature Postmark (X-Postmark-Signature, base64 HMAC SHA256 sur le body).
    """
    try:
        if not signature or not secret:
            return False
        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("ascii")
        # Comparaison constant-time
        return hmac.compare_digest(expected, signature.strip())
    except Exception:
        return False


def handle_postmark_bounce(raw_body: bytes) -> Tuple[int, str]:
    """
    Traite un webhook bounce Postmark (PII-safe):
    - Incrémente eotp_mail_bounce_total{type,domain}
    - Émet event mail:bounced
    - Ne stocke pas l'email; seulement domaine et type
    Retourne (status, message)
    """
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        # Postmark: "RecordType": "Bounce", "Type": "HardBounce"|"SoftBounce"|..., "Email": "user@domain"
        btype = (payload.get("Type") or "").strip()
        email = (payload.get("Email") or "").strip()
        dom = _email_domain(email) or ""
        labels = {"type": (btype.lower() or "unknown"), "domain": dom}
        _counter("eotp_mail_bounce_total", "E‑OTP emails bounces", labels=labels)
        record_auth_event(
            "mail",
            "bounced",
            realm=getattr(settings, "REALM_NAME", None),
            risk_score=None,
            fa_required=True,
        )
        return 200, "ok"
    except Exception as e:
        _counter("eotp_mail_provider_errors_total", "Erreurs provider mail (webhook parse)")
        return 400, f"bad_payload: {e}"
