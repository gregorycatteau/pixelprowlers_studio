# -*- coding: utf-8 -*-
# studio_core/urls.py
from __future__ import annotations

# Admin sécurisé (Custom AdminSite)
from accounts.admin import admin_site
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from django.views.generic import RedirectView

# OpenAPI schema views (drf-spectacular)
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

# JWT (DRF SimpleJWT) — compat héritée
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

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
    # =========================
    # API Agents (consommée par Nuxt)
    # =========================
    path("api/", include("api.views")),
    path("api/", include("ai_assistants.urls")),
]

# Debug toolbar + médias en dev
if settings.DEBUG:
    try:
        import debug_toolbar  # type: ignore

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except Exception:
        pass
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
