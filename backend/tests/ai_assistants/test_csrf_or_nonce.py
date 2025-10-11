import json
import time

import pytest
from ai_assistants.security import RequestNonce
from ai_assistants.views import GATE_SESSION_KEY, GATE_WHEN_KEY
from django.test import Client
from django.urls import reverse


def _prepare_client(superuser):
    client = Client(enforce_csrf_checks=True)
    client.force_login(superuser)
    session = client.session
    session[GATE_SESSION_KEY] = True
    session[GATE_WHEN_KEY] = time.time()
    session.save()
    return client


@pytest.mark.django_db(transaction=True)
@pytest.mark.agents
def test_request_without_nonce_is_rejected(client_logged, csrftoken):
    url = reverse("api_ask_agent", args=["bruce"])
    resp = client_logged.post(
        url,
        data=json.dumps({"message": "ping"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "nonce_missing"


@pytest.mark.django_db(transaction=True)
@pytest.mark.agents
def test_request_without_csrf_is_forbidden(superuser):
    client = _prepare_client(superuser)
    url = reverse("api_ask_agent", args=["bruce"])
    resp = client.post(
        url,
        data=json.dumps({"message": "ping"}),
        content_type="application/json",
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
    )
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.agents
def test_valid_nonce_and_csrf(client_logged, csrftoken):
    url = reverse("api_ask_agent", args=["bruce"])
    nonce = str(RequestNonce.generate())
    resp = client_logged.post(
        url,
        data=json.dumps({"message": "OK"}),
        content_type="application/json",
        HTTP_X_REQUEST_NONCE=nonce,
        HTTP_X_CSRFTOKEN=csrftoken,
    )
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
@pytest.mark.agents
def test_replay_nonce_rejected(client_logged, csrftoken):
    url = reverse("api_ask_agent", args=["bruce"])
    nonce = str(RequestNonce.generate())

    first = client_logged.post(
        url,
        data=json.dumps({"message": "once"}),
        content_type="application/json",
        HTTP_X_REQUEST_NONCE=nonce,
        HTTP_X_CSRFTOKEN=csrftoken,
    )
    assert first.status_code == 200

    replay = client_logged.post(
        url,
        data=json.dumps({"message": "twice"}),
        content_type="application/json",
        HTTP_X_REQUEST_NONCE=nonce,
        HTTP_X_CSRFTOKEN=csrftoken,
    )
    assert replay.status_code == 400
    assert replay.json()["error"] == "nonce_replay"
