# -*- coding: utf-8 -*-
# studio_core/urls.py
from __future__ import annotations

# Admin sécurisé (Custom AdminSite)
from accounts.admin import admin_site
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.middleware.csrf import get_token
from django.urls import include, path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import RedirectView

# OpenAPI schema views (drf-spectacular)
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from laby import views as laby_views

# JWT (DRF SimpleJWT) — compat héritée
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from studio_core.metrics import prometheus_text

from . import views
from .graphql_security import secure_graphql_view  # ← vue sécurisée (fonction)
from .honeypot import log_honeypot_hit  # ← logger IP/UA + compteur


def admin_honeypot(*args, **kwargs):
    """
    Faux endpoint /admin/ pour brouiller les scans automatisés.
    - Enregistre IP/UA + compteur (cache) et loggue l'événement.
    - Retourne 404 (aucune info divulguée).
    """
    request = args[0] if args else kwargs.get("request")
    if request is not None:
        log_honeypot_hit(request)
    return HttpResponseNotFound()


@ensure_csrf_cookie
def csrf_token(request):
    resp = JsonResponse({"ok": True, "csrf": get_token(request)}, status=200)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


urlpatterns = [
    # =========================
    # Admin sécurisé
    # =========================
    path("pp-admin/", admin_site.urls),
    # Redirections confort :
    # - sans slash -> avec slash
    re_path(r"^pp-admin$", RedirectView.as_view(url="/pp-admin/", permanent=False)),
    # - ancien chemin tapé par réflexe → nouveau chemin officiel
    path("pxp_admin/", RedirectView.as_view(url="/pp-admin/", permanent=False)),
    re_path(r"^pxp_admin$", RedirectView.as_view(url="/pp-admin/", permanent=False)),
    # Honeypot (facultatif) sur le chemin "classique"
    path("admin/", admin_honeypot, name="admin_honeypot"),
    # =========================
    # Probes (avec ET sans slash pour éviter 301)
    # =========================
    path("health", views.health, name="health_no_slash"),
    path("health/", views.health, name="health"),
    path("ready", views.ready, name="ready_no_slash"),
    path("ready/", views.ready, name="ready"),
    # =========================
    # REST test
    # =========================
    path("api/ping/", views.api_ping, name="api_ping"),
    path("api/auth/csrf/", csrf_token, name="csrf_token"),
    path("api/hello/", views.api_hello, name="api_hello"),
    path("_fa/verify", views.forward_auth_verify, name="forward_auth_verify"),
    path(".well-known/jwks.json", views.jwks_json, name="jwks_json"),
    path(
        "metrics",
        lambda request: HttpResponse(
            prometheus_text(), content_type="text/plain; version=0.0.4; charset=utf-8"
        ),
        name="metrics",
    ),
    # =========================
    # OpenAPI schema & docs (drf-spectacular)
    # =========================
    path("api/schema/", SpectacularAPIView.as_view(), name="api_schema"),
    path(
        "api/docs/swagger/",
        SpectacularSwaggerView.as_view(url_name="api_schema"),
        name="api_swagger_ui",
    ),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="api_schema"), name="api_redoc"),
    # =========================
    # GraphQL (vue sécurisée)
    # =========================
    path("graphql", secure_graphql_view, name="graphql_no_slash"),
    path("graphql/", secure_graphql_view, name="graphql"),
    # =========================
    # Auth JWT "legacy" (compat)
    # =========================
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # =========================
    # Accounts (login-cookie, refresh-cookie, whoami, etc.)
    # =========================
    path("api/accounts/", include("accounts.urls")),
    # Alias to expose /api/auth/* directly (frontend expects these)
    path("api/", include("accounts.urls")),
    # =========================
    # API Agents (consommée par Nuxt)
    # =========================
    path("api/", include("api.views")),
    path("api/", include("ai_assistants.urls")),
    # =========================
    # MCP serveur (consommé par les clients MCP)
    # =========================
    path("", include("mcp_server.urls")),
]

# Debug toolbar + médias en dev
if settings.DEBUG:
    try:
        import debug_toolbar  # type: ignore

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except Exception:
        pass
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Laby honeypot routes (only when Laby realm is active)
if getattr(settings, "REALM_NAME", "") == "laby":
    urlpatterns += [
        path("api/projects/", laby_views.api_projects_list, name="laby_projects_list"),
        path(
            "api/projects/<slug:slug>/", laby_views.api_projects_detail, name="laby_projects_detail"
        ),
        path("api/agents/", laby_views.api_agents_list, name="laby_agents_list"),
        path("api/agents/<slug:slug>/ask", laby_views.api_agents_ask, name="laby_agents_ask"),
        path("admin/login/", laby_views.admin_login_honeypot, name="laby_admin_login"),
        path("laby/health", laby_views.laby_health, name="laby_health"),
        path("artifacts/.env", laby_views.artifact_env, name="laby_artifact_env"),
        path("artifacts/id_ed25519", laby_views.artifact_id_ed25519, name="laby_artifact_key"),
        path(
            "artifacts/notes_admin.txt", laby_views.artifact_notes_admin, name="laby_artifact_notes"
        ),
    ]
