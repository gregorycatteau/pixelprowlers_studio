# pixelprowlers_studio/backend/studio_core/settings/realms/laby.py
# -*- coding: utf-8 -*-
"""
Realm settings — Laby (Honeypot)

Objectif
- Isoler complètement le realm “Laby” (antichambre/honeypot) avec:
  - Issuer/Audience JWT distincts des autres realms.
  - Noms de cookies spécifiques pour éviter toute collision inter-origines.
  - Comportements applicatifs identiques “en façade” mais sans effet de bord.
- Ce realm NE DOIT JAMAIS pointer vers des données de production.

Chargement
- Utiliser ce module comme DJANGO_SETTINGS_MODULE pour l’origin Honeypot
  (ex: laby.pixelprowlers.studio), ou l’importer comme base d’un settings
  d’environnement spécifique (staging/prod) du realm Laby.

Env attendues (suggestion)
- LABY_JWT_PRIVATE_KEY / LABY_JWT_PUBLIC_KEY (PEM RSA) — clés dédiées au realm.
- JWT_ISSUER / JWT_AUDIENCE (facultatif; valeurs par défaut ci-dessous).
- DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS pour affiner les hosts.
- SESSION_COOKIE_NAME / CSRF_COOKIE_NAME si personnalisation supplémentaire.

Notes
- La terminaison TLS, le filtrage (CrowdSec), et les décisions “front-door”
  (mTLS/forward_auth) sont gérés au reverse proxy.
- Ici, on cloisonne applicativement via cookies/origines/JWT distincts.
"""

from __future__ import annotations

import os

# Hérite de la config de prod (inclut security.py, CSP, logs, etc.)
# Attention: prod.py exige DATABASE_URL en environnement.
# Fournir un backend isolé (DB “honeypot”), jamais la base de prod.
from ..prod import *  # noqa: F401,F403

# ──────────────────────────────────────────────────────────────────────────────
# Realm metadata
# ──────────────────────────────────────────────────────────────────────────────

REALM_NAME = "laby"
REALM_HOST_DEFAULT = "laby.pixelprowlers.studio"
HONEYPOT_MODE = True  # Signal applicatif — ne pas lier à des effets réels

# ALLOWED_HOSTS & CSRF_TRUSTED_ORIGINS — spécifiques au realm Laby
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
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "pp_laby_sessionid")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "pp_laby_csrftoken")


# ──────────────────────────────────────────────────────────────────────────────
# JWT / SimpleJWT — issuer, audience, clés realm-spécifiques
# ──────────────────────────────────────────────────────────────────────────────

# Issuer/Audience dédiés (peuvent être surchargés par l'env)
REALM_JWT_ISSUER = os.getenv("JWT_ISSUER", f"https://{REALM_HOST_DEFAULT}")
REALM_JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "laby-honeypot")

# Clés RS256 spécifiques au realm (si fournies, elles préemptent la config de base)
LABY_JWT_PRIVATE_KEY = os.getenv("LABY_JWT_PRIVATE_KEY")  # -----BEGIN PRIVATE KEY----- ...
LABY_JWT_PUBLIC_KEY = os.getenv("LABY_JWT_PUBLIC_KEY")  # -----BEGIN PUBLIC KEY----- ...

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
        # Labbé/honeypot: conserver des durées courtes et rotation/blacklist héritées.
        # "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        # "REFRESH_TOKEN_LIFETIME": timedelta(hours=24),
    }
)

# Si des clés spécifiques au realm sont fournies, forcer RS256 avec ces clés
if LABY_JWT_PRIVATE_KEY and LABY_JWT_PUBLIC_KEY:
    SIMPLE_JWT.update(
        {
            "ALGORITHM": "RS256",
            "SIGNING_KEY": LABY_JWT_PRIVATE_KEY,
            "VERIFYING_KEY": LABY_JWT_PUBLIC_KEY,
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# Divers — ajustements spécifiques au realm Laby
# ──────────────────────────────────────────────────────────────────────────────

# Pas de fuite d’info côté DEBUG
DEBUG = False

# Cookies stricts (hérités de security.py/prod.py), rappel explicite
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# HSTS activé (hérité), redirection HTTPS côté app (en plus du reverse-proxy)
SECURE_SSL_REDIRECT = True

# Recommandations d’exploitation (documentaires, non opérationnelles ici):
# - Utiliser une base dédiée “honeypot” (DATABASE_URL distinct), sans données réelles.
# - Brancher des endpoints “plausibles” en lecture seule; toute écriture doit être
#   inerte (mock/no-op) côté vues sérialisées.
# - Journaliser les interactions (sans PII), avec un horodatage UTC et, idéalement,
#   un scellé journalier (hash) hors site.
