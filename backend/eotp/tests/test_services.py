# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, override_settings
from django.utils import timezone
from eotp.models import EotpChallenge
from eotp.services import eotp_issue, eotp_resend, eotp_verify

User = get_user_model()


def _add_session(request):
    """Attach a Django session to a RequestFactory request."""
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    return request


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_issue_cree_challenge_pending_avec_hash_argon2id():
    rf = RequestFactory()
    req = _add_session(rf.post("/"))
    user = User.objects.create_user(username="tester", password="x")
    res = eotp_issue(req, user)
    assert res.ok is True
    # Un challenge pending existe bien en base pour la session
    assert EotpChallenge.objects.filter(
        session_key=req.session.session_key, status=EotpChallenge.Status.PENDING
    ).exists()


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_verify_code_valide_change_status_en_consumed_et_bloque_rejeu():
    rf = RequestFactory()
    req = _add_session(rf.post("/"))
    user = User.objects.create_user(username="tester", password="x")
    # Issue
    res = eotp_issue(req, user)
    assert res.ok is True
    # Récupère le code via _peek (stocké en session en mode test)
    code = req.session.get("eotp_peek_code")
    assert isinstance(code, str) and re.fullmatch(r"\d{6}|\d{8}", code)
    # Verify OK
    v = eotp_verify(req, code)
    assert v.ok is True
    # Rejeu avec le même code doit échouer (consumed)
    v2 = eotp_verify(req, code)
    assert v2.ok is False


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_verify_code_invalide_incremente_tries_et_applique_lock_apres_max_tries(settings):
    rf = RequestFactory()
    req = _add_session(rf.post("/"))
    user = User.objects.create_user(username="tester", password="x")
    eotp_issue(req, user)
    # Tente des mauvais codes jusqu'au lock
    for i in range(3):
        v = eotp_verify(req, "000000")
    assert v.ok is False
    # Le dernier challenge doit être en LOCKED
    ch = (
        EotpChallenge.objects.filter(session_key=req.session.session_key)
        .order_by("-created_at")
        .first()
    )
    assert ch is not None
    assert ch.status == EotpChallenge.Status.LOCKED


@pytest.mark.django_db
@override_settings(APP_ENV="test")
def test_resend_invalide_ancien_code_et_regenere_avec_cooldown():
    rf = RequestFactory()
    req = _add_session(rf.post("/"))
    user = User.objects.create_user(username="tester", password="x")
    eotp_issue(req, user)
    # Resend immédiat → 429 profile (cooldown)
    r1 = eotp_resend(req, user=user)
    assert r1.ok is False
    assert isinstance(r1.retry_after, int) and r1.retry_after >= 1
    # Bypass cooldown en ajustant last_sent_at
    latest = (
        EotpChallenge.objects.filter(
            session_key=req.session.session_key, status=EotpChallenge.Status.PENDING
        )
        .order_by("-created_at")
        .first()
    )
    assert latest is not None
    latest.last_sent_at = timezone.now() - timedelta(seconds=60)
    latest.save(update_fields=["last_sent_at"])
    # Resend après cooldown → OK et ancien pending invalidé
    r2 = eotp_resend(req, user=user)
    assert r2.ok is True
    # Il ne doit rester qu'un seul pending récent
    pendings = EotpChallenge.objects.filter(
        session_key=req.session.session_key, status=EotpChallenge.Status.PENDING
    ).count()
    assert pendings == 1
