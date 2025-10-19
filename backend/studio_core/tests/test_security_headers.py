# -*- coding: utf-8 -*-
"""
S7 — test_headers_present_and_strict

Objectif:
- Vérifier la présence des en-têtes de sécurité sur une requête GET.
- Valeurs minimales attendues:
  - Strict-Transport-Security: présent (valeur exacte dépend de l'environnement/terminating TLS)
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY (ou SAMEORIGIN si backoffice)
  - Referrer-Policy: policy raisonnable (ex: no-referrer, strict-origin-when-cross-origin, etc.)
  - Permissions-Policy: restreint par défaut
  - Content-Security-Policy: CSP minimal compatible Nuxt

Notes:
- Ce test cible /health pour éviter auth/CSRf specifics.
- Il peut échouer si les en-têtes ne sont pas encore mis en place (TDD de durcissement).
"""

import pytest
from django.test import Client


@pytest.mark.django_db(transaction=False)
def test_headers_present_and_strict():
    client = Client()
    resp = client.get("/health")

    # Helper pour lire la valeur d'un header sans lever d'exception
    def get_header(name: str):
        try:
            # Django >= 3.2
            return resp.headers.get(name)  # type: ignore[attr-defined]
        except Exception:
            # Fallback générique
            return resp[name] if resp.has_header(name) else None

    required_headers = [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Content-Security-Policy",
    ]

    # Présence des en-têtes
    for h in required_headers:
        assert resp.has_header(h), f"Header manquant: {h}"

    # Valeurs minimales
    xcto = get_header("X-Content-Type-Options")
    assert (
        xcto is not None and xcto.lower() == "nosniff"
    ), f"X-Content-Type-Options attendu 'nosniff', reçu: {xcto}"

    xfo = get_header("X-Frame-Options")
    assert xfo in {
        "DENY",
        "SAMEORIGIN",
    }, f"X-Frame-Options attendu 'DENY' ou 'SAMEORIGIN', reçu: {xfo}"

    # La politique Referrer peut varier: valider présence d'une des politiques strictes usuelles
    refpol = (get_header("Referrer-Policy") or "").lower()
    allowed_refpol = {
        "no-referrer",
        "strict-origin",
        "strict-origin-when-cross-origin",
        "same-origin",
    }
    assert any(
        refpol.startswith(p) for p in allowed_refpol
    ), f"Referrer-Policy trop permissive: {refpol}"

    # Permissions-Policy: doit exister et ne pas être vide
    pp = get_header("Permissions-Policy")
    assert pp is not None and len(pp.strip()) > 0, "Permissions-Policy doit être définie"

    # CSP: doit exister et contenir au moins default-src
    csp = (get_header("Content-Security-Policy") or "").lower()
    assert "default-src" in csp, "CSP doit au minimum définir 'default-src'"

    # HSTS: présent (la valeur exacte dépendra de l'environnement/terminating TLS)
    hsts = get_header("Strict-Transport-Security")
    assert (
        hsts is not None and len(hsts.strip()) > 0
    ), "HSTS doit être défini (ex: max-age=31536000; includeSubDomains)"
