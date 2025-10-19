# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Callable

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, override_settings
from eotp.mailer import send_eotp_email
from eotp.services import eotp_issue, eotp_resend

User = get_user_model()


@pytest.mark.django_db
@override_settings(APP_ENV="dev")
def test_send_eotp_email_postmark_5xx_fallback_smtp(monkeypatch):
    """
    S2: si Postmark renvoie 5xx, fallback SMTP est tenté et peut réussir.
    - monkeypatch _postmark_request -> 500
    - monkeypatch send_mail -> 1
    - send_eotp_email(...) => True (fallback OK)
    """
    # Simuler Postmark en erreur
    import eotp.mailer as mailer

    monkeypatch.setenv("MAILER_PROVIDER", "postmark")
    monkeypatch.setenv("POSTMARK_API_TOKEN", "pm_test_token")
    monkeypatch.setenv("POSTMARK_FROM", "security@pixelprowlers.io")

    def fake_postmark_request(payload: dict, token: str):
        return 500, "error"

    def fake_send_mail(subject, message, from_email, recipient_list, fail_silently=False):
        return 1

    monkeypatch.setattr(mailer, "_postmark_request", fake_postmark_request)
    monkeypatch.setattr(mailer, "send_eotp_email", mailer.send_eotp_email)
    monkeypatch.setattr(mailer, "_send_via_smtp", lambda to, subj, body: True)
    # Appel
    ok = send_eotp_email("user@example.com", "123456", 300, corr_id="C-1")
    assert ok is True


@pytest.mark.django_db
@override_settings(APP_ENV="prod", POSTMARK_WEBHOOK_SECRET="shhhh_shared_secret")
def test_webhook_postmark_bounce_signature_ok(client: Client):
    """
    S2: Webhook bounces Postmark signature vérifiée OK -> 200.
    """
    payload = {
        "RecordType": "Bounce",
        "Type": "HardBounce",
        "Email": "user@example.com",
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = base64.b64encode(hmac.new(b"shhhh_shared_secret", raw, hashlib.sha256).digest()).decode(
        "ascii"
    )

    r = client.post(
        "/api/webhooks/postmark/bounce/",
        data=raw,
        content_type="application/json",
        HTTP_X_POSTMARK_SIGNATURE=sig,
    )
    assert r.status_code == 200, r.content
    body = json.loads(r.content.decode("utf-8"))
    assert body.get("ok") is True


@pytest.mark.django_db
@override_settings(APP_ENV="prod", POSTMARK_WEBHOOK_SECRET="shhhh_shared_secret")
def test_webhook_postmark_bounce_signature_ko(client: Client):
    """
    S2: Webhook bounces Postmark signature KO -> 403.
    """
    payload = {"RecordType": "Bounce", "Type": "SoftBounce", "Email": "user@example.com"}
    raw = json.dumps(payload).encode("utf-8")
    # Mauvaise signature
    r = client.post(
        "/api/webhooks/postmark/bounce/",
        data=raw,
        content_type="application/json",
        HTTP_X_POSTMARK_SIGNATURE="invalid",
    )
    assert r.status_code == 403


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_resend_quota_user_limit_3_per_hour(monkeypatch):
    """
    S2: quota utilisateur (3/h) lors de resend.
    - Après 3 resends OK, le 4e doit renvoyer ok=False avec retry_after.
    """
    # Neutraliser le cooldown session pour ce test de quota utilisateur
    monkeypatch.setenv("COOLDOWN_SECONDS", "0")
    # Le module eotp.services lit la valeur à l'import: forcer le constant à 0
    import eotp.services as svc  # type: ignore

    monkeypatch.setattr(svc, "EOTP_COOLDOWN_SECONDS", 0, raising=False)
    # Préparer requête avec session
    rf = RequestFactory()
    req = rf.post("/api/auth/2fa/email/resend/")
    # Attacher une session à la requête
    from django.contrib.sessions.middleware import SessionMiddleware

    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(req)
    req.session.save()

    # Utilisateur de test
    user = User.objects.create_user(
        username="quota_user", password="x", email="quota@pxp.test", is_active=True
    )

    # Emission initiale (issue) pour avoir un pending
    res_issue = eotp_issue(req, user=user)
    assert res_issue.ok is True

    # 3 resends OK
    for _ in range(3):
        rr = eotp_resend(req, user=user)
        assert rr.ok is True

    # 4e -> quota atteint
    rr4 = eotp_resend(req, user=user)
    assert rr4.ok is False
    assert int(rr4.retry_after or 0) > 0
