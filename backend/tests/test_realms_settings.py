# -*- coding: utf-8 -*-
"""
Tests — Realms settings isolation (Dojo/Clients/Laby)

Vérifie que chaque realm:
- définit des noms de cookies distincts (SESSION/CSRF),
- expose des claims JWT (ISSUER/AUDIENCE) distincts et plausibles,
- garde les drapeaux de sécurité (DEBUG False, SECURE_SSL_REDIRECT True).

Ces tests importent directement les modules de settings des realms pour valider
leur configuration statique sans initialiser Django (pas de client HTTP ici).
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Dict, Tuple

import pytest


def _reload_realm(modname: str, env_overrides: Dict[str, str] | None = None):
    """
    Recharge un module de settings realm avec des variables d'environnement
    contrôlées. On purge base/prod/security + le module realm ciblé pour forcer
    l'exécution avec le nouvel environnement.
    """
    purge = [
        "studio_core.settings.base",
        "studio_core.settings.security",
        "studio_core.settings.prod",
        modname,
    ]
    old_env = os.environ.copy()
    try:
        # Appliquer overrides d'env (ex: DATABASE_URL requis par prod.py)
        os.environ.update(env_overrides or {})

        # Purger les modules concernés pour forcer un re-import propre
        for name in purge:
            if name in sys.modules:
                del sys.modules[name]

        # Importer le realm ciblé
        return importlib.import_module(modname)
    finally:
        # Restaurer l'environnement initial
        # (les valeurs calculées sont déjà figées dans le module importé)
        os.environ.clear()
        os.environ.update(old_env)


# Jeu d’attendus par realm: (module, session_cookie, csrf_cookie, issuer, audience)
REALMS: Tuple[Tuple[str, str, str, str, str], ...] = (
    (
        "studio_core.settings.realms.dojo",
        "pp_dojo_sessionid",
        "pp_dojo_csrftoken",
        "https://dojo.pixelprowlers.studio",
        "dojo-admins",
    ),
    (
        "studio_core.settings.realms.clients",
        "pp_clients_sessionid",
        "pp_clients_csrftoken",
        "https://clients.pixelprowlers.studio",
        "clients-users",
    ),
    (
        "studio_core.settings.realms.laby",
        "pp_laby_sessionid",
        "pp_laby_csrftoken",
        "https://laby.pixelprowlers.studio",
        "laby-honeypot",
    ),
)


@pytest.mark.parametrize("modname, sess_cookie, csrf_cookie, issuer, audience", REALMS)
def test_realm_cookies_and_jwt_claims(modname, sess_cookie, csrf_cookie, issuer, audience):
    """
    Chaque realm doit:
    - exposer des noms de cookies spécifiques,
    - définir des claims JWT (ISSUER/AUDIENCE) propres au realm,
    - ne pas être en DEBUG et forcer la redirection HTTPS côté app.
    """
    # prod.py exige DATABASE_URL présent; fournir une valeur isolée pour les tests.
    env = {"DATABASE_URL": "sqlite:////tmp/pp_realm_test.db"}
    m = _reload_realm(modname, env_overrides=env)

    # Cookies
    assert getattr(m, "SESSION_COOKIE_NAME", "") == sess_cookie
    assert getattr(m, "CSRF_COOKIE_NAME", "") == csrf_cookie

    # Security flags
    assert getattr(m, "DEBUG", None) is False
    assert getattr(m, "SECURE_SSL_REDIRECT", None) is True

    # JWT claims
    sj = getattr(m, "SIMPLE_JWT", {})
    assert isinstance(sj, dict) and sj, "SIMPLE_JWT doit être défini"

    iss = sj.get("ISSUER")
    aud = sj.get("AUDIENCE")
    assert isinstance(iss, str) and iss, "ISSUER doit être une chaîne non vide"
    assert isinstance(aud, str) and aud, "AUDIENCE doit être une chaîne non vide"

    # Par défaut (sans override d'env), on attend les valeurs de base du realm
    assert iss == issuer
    assert aud == audience

    # Type d'auth header conservé
    auth_types = sj.get("AUTH_HEADER_TYPES")
    assert auth_types and "Bearer" in tuple(auth_types)


def test_realms_isolation_across_modules():
    """
    Vérifie l’isolation inter-realms: noms de cookies/ISSUER/AUDIENCE distincts.
    """
    env = {"DATABASE_URL": "sqlite:////tmp/pp_realm_test.db"}

    modules = [
        _reload_realm("studio_core.settings.realms.dojo", env_overrides=env),
        _reload_realm("studio_core.settings.realms.clients", env_overrides=env),
        _reload_realm("studio_core.settings.realms.laby", env_overrides=env),
    ]

    sess_names = {getattr(m, "SESSION_COOKIE_NAME", "") for m in modules}
    csrf_names = {getattr(m, "CSRF_COOKIE_NAME", "") for m in modules}
    issuers = {getattr(m, "SIMPLE_JWT", {}).get("ISSUER") for m in modules}
    audiences = {getattr(m, "SIMPLE_JWT", {}).get("AUDIENCE") for m in modules}

    # Unicité sur 3 realms
    assert len(sess_names) == 3 and "" not in sess_names
    assert len(csrf_names) == 3 and "" not in csrf_names
    assert len(issuers) == 3 and None not in issuers
    assert len(audiences) == 3 and None not in audiences
