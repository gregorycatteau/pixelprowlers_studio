# backend/studio_core/settings/security.py
# -*- coding: utf-8 -*-
"""
Durcissement sécurité commun (chargé par prod.py).
Chaque variable peut être surchargée via l'environnement.
Toutes les options ici sont pensées pour la PRODUCTION.

⚠️ En DEV, ne charge PAS ce module (ou surcharges via env) pour éviter les contraintes HTTPS.
"""

import os
from datetime import timedelta


def _get_bool(name: str, default: bool = False) -> bool:
    """Retourne un booléen depuis l'env (1/true/on/yes)."""
    return os.getenv(name, str(int(default))).lower() in ("1", "true", "on", "yes")


# --- HTTPS & HSTS ---
# Active la redirection HTTPS côté Django (en plus de Traefik/Nginx)
SECURE_SSL_REDIRECT = _get_bool("SECURE_SSL_REDIRECT", True)

# HSTS pour bloquer le downgrade HTTP (contre SSLStrip & co)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))  # 1 an
SECURE_HSTS_INCLUDE_SUBDOMAINS = _get_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _get_bool("SECURE_HSTS_PRELOAD", True)

# Indique à Django qu'il est derrière un proxy TLS (Traefik/Nginx)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# --- Cookies & CSRF ---
SESSION_COOKIE_SECURE = _get_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _get_bool("CSRF_COOKIE_SECURE", True)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Stratégies SameSite (Strict pour sessions, Lax pour CSRF)
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# --- En-têtes de protection ---
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")  # anti-clickjacking
# (Depuis Django 4+, XSS filter legacy n'est plus nécessaire, conservé pour compat)
SECURE_BROWSER_XSS_FILTER = True

# --- JWT / Sessions (exemple) ---
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MIN", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
ACCESS_TOKEN_LIFETIME = timedelta(minutes=ACCESS_TOKEN_MINUTES)
REFRESH_TOKEN_LIFETIME = timedelta(days=REFRESH_TOKEN_DAYS)
JWT_SIGNING_ALGORITHM = os.getenv("JWT_SIGNING_ALGORITHM", "HS512")
