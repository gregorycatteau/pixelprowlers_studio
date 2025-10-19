# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from eotp.passphrase import (
    PASS_ENABLE,
    PASS_REQUIRED,
    set_passphrase_for_user,
    verify_passphrase_for_user,
)
from studio_core.metrics_adapter import counter_inc


@require_POST
@csrf_protect
def api_auth_eotp_passphrase_set(request):
    """
    POST /api/auth/2fa/passphrase/set/
    Body: { "passphrase": "..." }
    Contexte attendu: pending_2fa_user en session.
    Flags: PASS_ENABLE doit être True.
    Réponses:
      200 { ok: true }
      400/403 génériques sinon (PII-safe)
    """
    if not PASS_ENABLE:
        return JsonResponse({"ok": False, "error": "not_allowed"}, status=403)

    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    phrase = (data.get("passphrase") or "").strip()
    if not phrase:
        return JsonResponse({"ok": False, "error": "invalid"}, status=400)

    ok = set_passphrase_for_user(int(user_id), phrase)
    if not ok:
        return JsonResponse({"ok": False, "error": "set_failed"}, status=500)

    # Si PASS_REQUIRED, on marque la session comme nécessitant vérif
    try:
        if PASS_REQUIRED:
            request.session["pass_required"] = True
            request.session["pass_ok"] = False
            request.session.modified = True
    except Exception:
        pass

    return JsonResponse({"ok": True}, status=200)


@require_POST
@csrf_protect
def api_auth_eotp_passphrase_verify(request):
    """
    POST /api/auth/2fa/passphrase/verify/
    Body: { "passphrase": "..." }
    Vérifie la passphrase pour pending_2fa_user. En succès: session.pass_ok=True.
    Réponses:
      200 { ok: true }
      403 { ok: false, error: "invalid" } (générique) + compteur eotp_passphrase_failed_total
    """
    if not PASS_ENABLE:
        return JsonResponse({"ok": False, "error": "not_allowed"}, status=403)

    user_id = request.session.get("pending_2fa_user")
    if not user_id:
        return JsonResponse({"ok": False, "error": "invalid_state"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return JsonResponse({"ok": False, "error": "bad_json"}, status=400)

    phrase = (data.get("passphrase") or "").strip()
    if not phrase:
        counter_inc("eotp_passphrase_failed_total")
        return JsonResponse({"ok": False, "error": "invalid"}, status=403)

    ok = verify_passphrase_for_user(int(user_id), phrase)
    if not ok:
        counter_inc("eotp_passphrase_failed_total")
        return JsonResponse({"ok": False, "error": "invalid"}, status=403)

    try:
        request.session["pass_required"] = True  # explicite le besoin et la validation
        request.session["pass_ok"] = True
        request.session.modified = True
    except Exception:
        pass

    return JsonResponse({"ok": True}, status=200)
