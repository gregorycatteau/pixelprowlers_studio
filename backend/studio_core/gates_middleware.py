# studio_core/gates_middleware.py
# -*- coding: utf-8 -*-
from django.http import JsonResponse
from django.utils import timezone

GATE_SESSION_KEY = "pp_gate_ok"
GATE_WHEN_KEY = "pp_gate_ts"
GATE_TTL_MINUTES = 90  # durée de validité du gate


class GatedSessionMiddleware:
    """
    Exige que la session ait franchi le gate (absurdité + rituel) pour /api/agents/*.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.rstrip("/")
        if path.startswith("/api/agents"):
            ok = request.session.get(GATE_SESSION_KEY, False)
            ts = request.session.get(GATE_WHEN_KEY)
            if not ok or not ts:
                return JsonResponse({"ok": False, "error": "gate_required"}, status=403)
            # TTL
            if (
                timezone.now() - timezone.make_aware(timezone.datetime.fromtimestamp(ts))
            ).total_seconds() > GATE_TTL_MINUTES * 60:
                for k in (GATE_SESSION_KEY, GATE_WHEN_KEY):
                    request.session.pop(k, None)
                return JsonResponse({"ok": False, "error": "gate_expired"}, status=403)
        return self.get_response(request)
