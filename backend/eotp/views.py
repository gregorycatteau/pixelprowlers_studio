# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Tuple

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .mailer import handle_postmark_bounce, verify_postmark_webhook_signature


def _json_error(status: int, msg: str) -> JsonResponse:
    resp = JsonResponse({"ok": False, "error": msg}, status=status)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@csrf_exempt
@require_POST
def webhook_postmark_bounce(request: HttpRequest) -> HttpResponse:
    """
    POST /api/webhooks/postmark/bounce/
    Sécurisé par signature HMAC SHA-256 (Base64) sur le body:
      - Header: X-Postmark-Signature
      - Secret: POSTMARK_WEBHOOK_SECRET (env)

    PII-safe:
      - On ne stocke pas l'email complet.
      - handle_postmark_bounce() incrémente des métriques par {type,domain}
        et émet un event mail:bounced.
    """
    secret = (getattr(settings, "POSTMARK_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        # Permettre le test local sans secret, mais refuser en prod
        app_env = (getattr(settings, "APP_ENV", "") or "").strip().lower()
        if app_env in ("prod", "production"):
            return _json_error(403, "webhook_not_configured")

    raw = request.body or b""
    sig = request.headers.get("X-Postmark-Signature", "").strip()

    if secret:
        if not sig or not verify_postmark_webhook_signature(raw, sig, secret):
            return _json_error(403, "invalid_signature")

    status, msg = handle_postmark_bounce(raw)
    if status >= 200 and status < 300:
        return JsonResponse({"ok": True, "message": msg}, status=status)
    return _json_error(status, msg)
