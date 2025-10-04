# studio_core/api_auth_middleware.py
# -*- coding: utf-8 -*-
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import resolve_url


class ApiAuthRedirectTo401Middleware:
    """
    Convertit les redirects vers LOGIN_URL en 401 JSON pour les endpoints /api/*.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.login_url = resolve_url(getattr(settings, "LOGIN_URL", "/pp-admin/login/"))

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/") and 300 <= response.status_code < 400:
            loc = response.headers.get("Location", "")
            if loc.startswith(self.login_url):
                return JsonResponse({"ok": False, "error": "auth_required"}, status=401)
        return response
