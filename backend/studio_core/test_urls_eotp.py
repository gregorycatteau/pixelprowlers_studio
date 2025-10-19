# -*- coding: utf-8 -*-
"""
URLConf minimal de test pour e-OTP (évitant l'import de accounts.admin/admin site).

Expose uniquement les endpoints nécessaires aux tests d'intégration e-OTP:
- /api/auth/login-cookie/
- /api/auth/login/
- /api/auth/2fa/email/verify/
- /api/auth/2fa/email/resend/
- /api/auth/2fa/email/_peek/
"""

from __future__ import annotations

from django.core.cache import cache
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from eotp import views as eotp_views
from studio_core import views as core_views


def ready(_request):
    return JsonResponse({"status": "ok"})


@ensure_csrf_cookie
def csrf_token(_request):
    # Force set CSRF cookie and return token for API clients (Playwright)
    token = get_token(_request)
    return JsonResponse({"csrfToken": token})


def flush(_request):
    # Test-only: clear cache (quota, cooldown counters, pending eotp cache if any)
    try:
        cache.clear()
        return JsonResponse({"ok": True})
    except Exception:
        return JsonResponse({"ok": False}, status=500)


urlpatterns = [
    path("ready/", ready, name="ready"),
    path("csrf/", csrf_token, name="csrf_token"),
    path("flush/", flush, name="flush_cache"),
    path("api/", include("accounts.urls")),
    path(
        "api/webhooks/postmark/bounce/", eotp_views.webhook_postmark_bounce, name="postmark_bounce"
    ),
    # Debug e-OTP stats (DEV/TEST only; gated in view)
    path("debug/eotp-stats", core_views.debug_eotp_stats, name="debug_eotp_stats"),
    path("debug/eotp-stats/", core_views.debug_eotp_stats, name="debug_eotp_stats_slash"),
]
