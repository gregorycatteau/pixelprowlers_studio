# pixelprowlers_studio/backend/studio_core/settings/realms/clients.py
# -*- coding: utf-8 -*-
"""
Realm settings — Clients (Accredited users)

Objectif
- Isoler le realm "Clients" avec un issuer/audience JWT distincts.
- Allouer des noms de cookies spécifiques pour éviter toute collision inter-origines.
- Conserver le durcissement de prod (security.py) en surchargeant uniquement
  les éléments liés à l’authN/realm.

Chargement
- Utiliser ce module comme DJANGO_SETTINGS_MODULE pour l’origin Clients
  (ex: clients.pixelprowlers.studio), ou l’importer comme base d’un settings
  d’environnement spécifique (staging/prod) du realm Clients.

Env attendues (suggestion)
- CLIENTS_JWT_PRIVATE_KEY / CLIENTS_JWT_PUBLIC_KEY (PEM RSA) — clés dédiées au realm.
- JWT_ISSUER / JWT_AUDIENCE (facultatif; valeurs par défaut ci-dessous).
- DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS pour affiner les hosts.
- SESSION_COOKIE_NAME / CSRF_COOKIE_NAME si personnalisation supplémentaire.

Notes
- Terminaison TLS et éventuels contrôles front-door (CrowdSec/Turnstile/forward_auth)
  se font au reverse proxy; ici on cloisonne applicativement.
"""

from __future__ import annotations

import os

# Hérite de la config de prod (inclut security.py, CSP, logs, etc.)
from ..prod import *  # noqa: F401,F403

# ──────────────────────────────────────────────────────────────────────────────
# Realm metadata
# ──────────────────────────────────────────────────────────────────────────────

REALM_NAME = "clients"
REALM_HOST_DEFAULT = "clients.pixelprowlers.studio"

# ALLOWED_HOSTS & CSRF_TRUSTED_ORIGINS — spécifiques au realm Clients
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
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "pp_clients_sessionid")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "pp_clients_csrftoken")


# ──────────────────────────────────────────────────────────────────────────────
# JWT / SimpleJWT — issuer, audience, clés realm-spécifiques
# ──────────────────────────────────────────────────────────────────────────────

# Issuer/Audience dédiés (peuvent être surchargés par l'env)
REALM_JWT_ISSUER = os.getenv("JWT_ISSUER", f"https://{REALM_HOST_DEFAULT}")
REALM_JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "clients-users")

# Clés RS256 spécifiques au realm (si fournies, elles préemptent la config de base)
CLIENTS_JWT_PRIVATE_KEY = os.getenv("CLIENTS_JWT_PRIVATE_KEY")  # -----BEGIN PRIVATE KEY----- ...
CLIENTS_JWT_PUBLIC_KEY = os.getenv("CLIENTS_JWT_PUBLIC_KEY")  # -----BEGIN PUBLIC KEY----- ...

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
        "AUTH_HEADER_TYPES": ("Bearer",),
        # Access/Refresh lifetimes hérités de base/prod; ajustables si besoin :
        # "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
        # "REFRESH_TOKEN_LIFETIME": timedelta(hours=24),
    }
)

# Si des clés spécifiques au realm sont fournies, forcer RS256 avec ces clés
if CLIENTS_JWT_PRIVATE_KEY and CLIENTS_JWT_PUBLIC_KEY:
    SIMPLE_JWT.update(
        {
            "ALGORITHM": "RS256",
            "SIGNING_KEY": CLIENTS_JWT_PRIVATE_KEY,
            "VERIFYING_KEY": CLIENTS_JWT_PUBLIC_KEY,
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# Divers — ajustements spécifiques au realm Clients
# ──────────────────────────────────────────────────────────────────────────────

# Pas de fuite d’info côté DEBUG
DEBUG = False

# Cookies stricts (hérités de security.py/prod.py), rappel explicite
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")  # UX un peu moins stricte
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# HSTS activé (hérité), redirection HTTPS côté app (en plus du reverse-proxy)
SECURE_SSL_REDIRECT = True

# Remarques:
# - Les mécanismes MFA (ex: TOTP côté clients) et rate-limits DRF sont
#   configurés au niveau du projet; ce module se concentre sur l’isolation
#   realm (origines/cookies/JWT).
