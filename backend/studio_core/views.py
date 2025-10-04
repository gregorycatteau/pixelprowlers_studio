# studio_core/views.py
from __future__ import annotations

import os

from django.db import connection
from django.http import JsonResponse


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
