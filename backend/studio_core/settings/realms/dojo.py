# backend/studio_core/settings/realms/dojo.py
# -*- coding: utf-8 -*-
"""
Realm settings — Dojo (Admins)

Objectif
- Isoler le realm "Dojo" (admins) avec un issuer/audience JWT distincts et,
  idéalement, des clés RS256 dédiées.
- Renforcer l’isolation via noms de cookies spécifiques au realm.
- Conserver le durcissement de prod (security.py) tout en surchargant ce qui
  concerne l’authN/realm.

Chargement
- Utiliser ce module comme DJANGO_SETTINGS_MODULE pour l’origin Admin
  (ex: dojo.pixelprowlers.studio), ou l’importer comme base d’un settings
  d’environnement spécifique (staging/prod) du realm Dojo.

Env attendues (suggestion)
- DOJO_JWT_PRIVATE_KEY / DOJO_JWT_PUBLIC_KEY (PEM RSA) — clés dédiées au realm
- JWT_ISSUER / JWT_AUDIENCE (facultatif; valeurs par défaut ci-dessous)
- DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS pour affiner les hosts
- SESSION_COOKIE_NAME / CSRF_COOKIE_NAME si personnalisation supplémentaire

Notes
- La terminaison TLS + mTLS client se fait au reverse proxy (Caddy).
- Ici, on fixe l’issuer/audience et on peut surcharger les clés si exposées
  via variables d’env spécifiques au realm.
"""

from __future__ import annotations

import os

# Hérite de la config de prod (inclut security.py, CSP, logs, etc.)
from ..prod import *  # noqa: F401,F403

# Enable django.contrib.sites and allauth (WebAuthn) for Dojo realm
if "django.contrib.sites" not in INSTALLED_APPS:
    INSTALLED_APPS.append("django.contrib.sites")
for app in ("allauth", "allauth.account", "allauth.mfa"):
    if app not in INSTALLED_APPS:
        INSTALLED_APPS.append(app)

# SITE_ID and account auth configuration (realm-level)
SITE_ID = int(os.getenv("SITE_ID", "1") or "1")
ACCOUNT_AUTHENTICATION_METHOD = os.getenv("ACCOUNT_AUTHENTICATION_METHOD", "email")
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "none")

# Ensure allauth auth backend is enabled (in addition to Django's)
try:
    AUTHENTICATION_BACKENDS  # noqa: F401
except NameError:
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
        "allauth.account.auth_backends.AuthenticationBackend",
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Realm metadata
# ──────────────────────────────────────────────────────────────────────────────

REALM_NAME = "dojo"
REALM_HOST_DEFAULT = "dojo.pixelprowlers.studio"

# ALLOWED_HOSTS & CSRF_TRUSTED_ORIGINS — spécifiques au realm admin
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", REALM_HOST_DEFAULT).split(",") if h.strip()
]

# Construit origins https://<host> pour CSRF_TRUSTED_ORIGINS si non fournis
_default_csrf = ",".join(f"https://{h}" for h in ALLOWED_HOSTS if h)
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", _default_csrf).split(",")
    if o.strip()
]

# CORS (realm) — origines strictes et cookies cross-site autorisés pour l’auth SSR
try:
    import corsheaders  # type: ignore  # noqa: F401

    if "corsheaders" not in INSTALLED_APPS:
        INSTALLED_APPS.append("corsheaders")
    if "corsheaders.middleware.CorsMiddleware" not in MIDDLEWARE:
        MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware"] + MIDDLEWARE
    # Autoriser uniquement les origines HTTPS correspondant aux ALLOWED_HOSTS de ce realm
    CORS_ALLOWED_ORIGINS = [
        f"https://{h.strip()}" for h in ALLOWED_HOSTS if h and not h.strip().startswith("http")
    ]
    CORS_ALLOW_CREDENTIALS = True
    # Vary: Origin est géré automatiquement par django-cors-headers
except Exception:
    pass

# Cookies nommés par realm pour éviter collisions inter-origines
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "pp_dojo_sessionid")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "pp_dojo_csrftoken")


# ──────────────────────────────────────────────────────────────────────────────
# JWT / SimpleJWT — issuer, audience, clés realm-spécifiques
# ──────────────────────────────────────────────────────────────────────────────

# Issuer/Audience dédiés (peuvent être surchargés par l'env)
REALM_JWT_ISSUER = os.getenv("JWT_ISSUER", f"https://{REALM_HOST_DEFAULT}")
REALM_JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "dojo-admins")

# Clés RS256 spécifiques au realm (si fournies, elles préemptent la config de base)
DOJO_JWT_PRIVATE_KEY = os.getenv("DOJO_JWT_PRIVATE_KEY")  # -----BEGIN PRIVATE KEY----- ...
DOJO_JWT_PUBLIC_KEY = os.getenv("DOJO_JWT_PUBLIC_KEY")  # -----BEGIN PUBLIC KEY----- ...

# S’assurer que SIMPLE_JWT existe (défini dans base.py via clés globales)
try:
    SIMPLE_JWT  # type: ignore  # noqa: F401
except NameError:
    SIMPLE_JWT = {}  # type: ignore

# Met à jour les paramètres d’issuer/audience pour ce realm
SIMPLE_JWT.update(
    {
        "ISSUER": REALM_JWT_ISSUER,
        "AUDIENCE": REALM_JWT_AUDIENCE,
        # Renforce le header type si utile (par défaut "Bearer")
        "AUTH_HEADER_TYPES": ("Bearer",),
        # Accès court (admins) — laisser tel quel si déjà défini dans base/prod
        # "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        # "REFRESH_TOKEN_LIFETIME": timedelta(hours=24),
    }
)

# Si des clés spécifiques au realm sont fournies, forcer RS256 avec ces clés
if DOJO_JWT_PRIVATE_KEY and DOJO_JWT_PUBLIC_KEY:
    SIMPLE_JWT.update(
        {
            "ALGORITHM": "RS256",
            "SIGNING_KEY": DOJO_JWT_PRIVATE_KEY,
            "VERIFYING_KEY": DOJO_JWT_PUBLIC_KEY,
        }
    )

# Optionnel: activer une audience de vérification stricte côté PyJWT
# (drf-simplejwt utilise AUDIENCE/ISSUER si fournis pour la validation)


# ──────────────────────────────────────────────────────────────────────────────
# REST Framework — rappel (hérite déjà de prod/base)
# ──────────────────────────────────────────────────────────────────────────────
# Ici, on peut resserrer si nécessaire (admins uniquement via JWT),
# mais on conserve la configuration héritée qui impose IsAuthenticated
# + JWTAuthentication par défaut. Exemple (décommenter si besoin) :
#
# REST_FRAMEWORK.update(
#     {
#         "DEFAULT_AUTHENTICATION_CLASSES": (
#             "rest_framework_simplejwt.authentication.JWTAuthentication",
#         ),
#         "DEFAULT_PERMISSION_CLASSES": (
#             "rest_framework.permissions.IsAuthenticated",
#         ),
#     }
# )


# ──────────────────────────────────────────────────────────────────────────────
# Divers — ajustements spécifiques au realm admin
# ──────────────────────────────────────────────────────────────────────────────

# On interdit toute fuite d’info côté DEBUG
DEBUG = False

# Cookies stricts (hérités de security.py/ prod.py), rappel explicite
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# HSTS activé (hérité), redirection HTTPS côté app (en plus du reverse-proxy)
SECURE_SSL_REDIRECT = True

# Note: l’auth mTLS se fait en amont (Caddy). Côté Django, on ne tente pas
# d’interpréter les certs client; on s’appuie sur l’issuer/audience et les
# clés RS256 distinctes pour cloisonner le realm Dojo au niveau applicatif.
