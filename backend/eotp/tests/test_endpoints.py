# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.utils import timezone
from eotp.models import EotpChallenge

User = get_user_model()


def csrf_client() -> Client:
    """
    Client avec vérification CSRF activée. Utilise le flux GET /auth/login-cookie/
    pour obtenir un csrftoken (déposé côté serveur).
    """
    client = Client(enforce_csrf_checks=True)
    # Dépose un csrftoken côté serveur
    resp = client.get("/api/auth/login-cookie/")
    assert resp.status_code in (200, 204)
    # Récup cookie csrftoken
    csrft = None
    for c in client.cookies.values():
        if c.key == "csrftoken":
            csrft = c.value
            break
    assert csrft, "csrftoken manquant sur client CSRF"
    return client


def csrf_headers_from_client(client: Client) -> dict:
    csrft = None
    for c in client.cookies.values():
        if c.key == "csrftoken":
            csrft = c.value
            break
    return {"HTTP_X_CSRFTOKEN": csrft or ""}


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_eotp_verify_flow_ok_and_errors_with_csrf():
    """
    - Login -> pending_2fa pour un superuser
    - _peek -> récupère le code
    - verify OK -> 200
    - verify mauvais code -> 401
    - modifier expires_at -> verify -> 403
    """
    # Arrange: user superuser
    user = User.objects.create_user(
        username="root", password="toor", is_superuser=True, is_active=True
    )

    client = csrf_client()
    h = csrf_headers_from_client(client)

    # 1) Login pour déclencher pending_2fa et émission e-OTP (via services)
    payload = {"username": "root", "password": "toor"}
    r = client.post(
        "/api/auth/login/",
        data=json.dumps(payload),
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    assert r.status_code == 200, r.content
    body = json.loads(r.content.decode("utf-8"))
    assert body.get("status") == "pending_2fa"

    # 2) _peek (APP_ENV=test) -> récupère le code en clair côté session
    r2 = client.post("/api/auth/2fa/email/_peek/")
    assert r2.status_code == 200, r2.content
    peek = json.loads(r2.content.decode("utf-8"))
    code = str(peek.get("code") or "")
    assert re.fullmatch(r"\d{6}|\d{8}", code)

    # 3) verify OK
    r3 = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": code}),
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    assert r3.status_code == 200, r3.content

    # 4) verify mauvais code -> 401
    r4 = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": "000000"}),
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    # Après succès précédent, la session n'est plus en pending_2fa -> on attend un 401 générique
    assert r4.status_code in (401, 403)

    # 5) Re-créer un pending récent puis forcer expires_at dans le passé pour tester 403
    # Re-login pour recréer pending_2fa
    r5 = client.post(
        "/api/auth/login/",
        data=json.dumps(payload),
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    assert r5.status_code == 200, r5.content
    # Trouver le dernier challenge et le faire expirer
    sess_key = client.session.session_key
    ch = EotpChallenge.objects.filter(session_key=sess_key).order_by("-created_at").first()
    assert ch is not None
    now = timezone.now()
    # Respecte la contrainte CHECK (expires_at > created_at) tout en simulant l'expiration.
    ch.created_at = now - timedelta(hours=1)
    ch.expires_at = now - timedelta(seconds=1)
    ch.save(update_fields=["created_at", "expires_at"])

    r6 = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": "999999"}),  # n'a pas d'importance ici
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    # API retourne 403 pour expired (mappé dans la vue)
    assert r6.status_code == 403, r6.content


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_eotp_resend_returns_retry_after_header_and_body():
    """
    - Login -> pending_2fa
    - resend -> 200 + Retry-After (header) + body {retry_after, expires_in}
    """
    user = User.objects.create_user(
        username="root2", password="toor", is_superuser=True, is_active=True
    )
    client = csrf_client()
    h = csrf_headers_from_client(client)

    # Login -> pending_2fa
    r = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": "root2", "password": "toor"}),
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    assert r.status_code == 200, r.content

    # Immediate resend may be 429 due to cooldown; bypass by rewinding last_sent_at
    sess_key = client.session.session_key
    latest = (
        EotpChallenge.objects.filter(session_key=sess_key, status=EotpChallenge.Status.PENDING)
        .order_by("-created_at")
        .first()
    )
    assert latest is not None
    latest.last_sent_at = timezone.now() - timedelta(seconds=120)
    latest.save(update_fields=["last_sent_at"])

    # Resend -> 200 + Retry-After header + payload fields
    r2 = client.post(
        "/api/auth/2fa/email/resend/",
        data=b"",
        content_type="application/json",
        **csrf_headers_from_client(client),
    )
    assert r2.status_code == 200, r2.content
    assert r2.headers.get("Retry-After"), "Retry-After header manquant"
    body = json.loads(r2.content.decode("utf-8"))
    assert body.get("ok") is True
    assert isinstance(body.get("retry_after"), int)
    assert isinstance(body.get("expires_in"), int)


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_csrf_missing_is_rejected_with_403():
    """
    - Sans header CSRF (enforce_csrf_checks=True), POST verify doit renvoyer 403.
    """
    user = User.objects.create_user(
        username="root3", password="toor", is_superuser=True, is_active=True
    )

    client = Client(enforce_csrf_checks=True)
    # Ne pas appeler /login-cookie/ pour ne pas déposer de csrftoken
    # On doit tout de même avoir une session et un pending_2fa pour aller jusque-là.
    # On prépare la session en appelant login sans CSRF -> attendu 403 directement si CSRF check avant vue.
    r = client.post(
        "/api/auth/login/",
        data=json.dumps({"username": "root3", "password": "toor"}),
        content_type="application/json",
    )
    # Certains middlewares peuvent encore laisser passer la première requête; assure qu'un POST verify est refusé
    r2 = client.post(
        "/api/auth/2fa/email/verify/",
        data=json.dumps({"code": "000000"}),
        content_type="application/json",
    )
    assert r2.status_code == 403, r2.content
