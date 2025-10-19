import json

import pytest
from ai_assistants.models import Conversation
from ai_assistants.security import RequestNonce
from django.urls import reverse


def _nonce_header(response=None) -> str:
    header = None
    if response is not None:
        header = response.headers.get("X-New-Request-Nonce")
    return header or str(RequestNonce.generate())


@pytest.mark.django_db(transaction=True)
def test_nonce_endpoint_requires_csrf(client_logged):
    url = reverse("api_auth_nonce")
    resp = client_logged.post(url)
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_nonce_endpoint_returns_signed_nonce(client_logged, csrftoken):
    url = reverse("api_auth_nonce")
    resp = client_logged.post(url, HTTP_X_CSRFTOKEN=csrftoken)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["nonce"]
    assert body["expires_in"] == RequestNonce.ttl_seconds
    assert resp.headers.get("X-New-Request-Nonce")


@pytest.mark.django_db(transaction=True)
def test_conversation_crud_flow(client_logged, csrftoken, dojo_agent):
    create_url = reverse("dojo-conversation-list")
    payload = {"agent": dojo_agent.slug, "title": "Sprint Run"}
    nonce = str(RequestNonce.generate())
    create_resp = client_logged.post(
        create_url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=nonce,
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    conv_id = data["id"]
    assert data["agent"] == dojo_agent.slug
    assert Conversation.objects.filter(id=conv_id, creator__username="security_ops").exists()

    list_resp = client_logged.get(create_url)
    assert list_resp.status_code == 200
    results = list_resp.json()
    assert results["count"] == 1
    assert results["results"][0]["id"] == conv_id

    detail_url = reverse("dojo-conversation-detail", args=[conv_id])
    update_nonce = _nonce_header(create_resp)
    update_resp = client_logged.patch(
        detail_url,
        data=json.dumps({"title": "Sprint Retro", "status": "closed"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=update_nonce,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["title"] == "Sprint Retro"
    assert updated["status"] == "closed"

    archive_nonce = _nonce_header(update_resp)
    delete_resp = client_logged.delete(
        detail_url,
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=archive_nonce,
    )
    assert delete_resp.status_code == 204
    assert Conversation.objects.get(id=conv_id).status == Conversation.STATUS_ARCHIVED


@pytest.mark.django_db(transaction=True)
def test_conversation_agent_immutable(client_logged, csrftoken, dojo_agent):
    create = client_logged.post(
        reverse("dojo-conversation-list"),
        data=json.dumps({"agent": dojo_agent.slug}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
    )
    assert create.status_code == 201
    conv_id = create.json()["id"]
    detail = reverse("dojo-conversation-detail", args=[conv_id])
    resp = client_logged.patch(
        detail,
        data=json.dumps({"agent": "other"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=_nonce_header(create),
    )
    assert resp.status_code == 400
    assert resp.json()["agent"] == ["immutable"]


@pytest.mark.django_db(transaction=True)
def test_message_create_and_list(client_logged, csrftoken, dojo_agent):
    create_conv = client_logged.post(
        reverse("dojo-conversation-list"),
        data=json.dumps({"agent": dojo_agent.slug, "title": "Daily"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
    )
    conv_id = create_conv.json()["id"]

    message_resp = client_logged.post(
        reverse("dojo-message-list"),
        data=json.dumps({"conversation": conv_id, "content": "Bonjour Dojo"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=_nonce_header(create_conv),
    )
    assert message_resp.status_code == 201
    message_body = message_resp.json()
    assert message_body["conversation"] == conv_id
    assert message_body["role"] == "user"

    list_resp = client_logged.get(
        reverse("dojo-message-list"),
        data={"conversation": conv_id},
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["count"] == 1
    assert body["results"][0]["content"] == "Bonjour Dojo"


@pytest.mark.django_db(transaction=True)
def test_message_list_requires_conversation_query(client_logged):
    resp = client_logged.get(reverse("dojo-message-list"))
    assert resp.status_code == 400
    assert resp.json()["conversation"] == ["required"]


@pytest.mark.django_db(transaction=True)
def test_nonce_replay_rejected(client_logged, csrftoken, dojo_agent):
    nonce = str(RequestNonce.generate())
    payload = {"agent": dojo_agent.slug}
    url = reverse("dojo-conversation-list")
    first = client_logged.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=nonce,
    )
    assert first.status_code == 201

    replay = client_logged.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=nonce,
    )
    assert replay.status_code == 400
    assert replay.json()["error"] == "nonce_replay"


@pytest.mark.django_db(transaction=True)
def test_cannot_post_message_to_archived_conversation(client_logged, csrftoken, dojo_agent):
    create_resp = client_logged.post(
        reverse("dojo-conversation-list"),
        data=json.dumps({"agent": dojo_agent.slug}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
    )
    conv_id = create_resp.json()["id"]
    detail_url = reverse("dojo-conversation-detail", args=[conv_id])
    client_logged.delete(
        detail_url,
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=_nonce_header(create_resp),
    )
    resp = client_logged.post(
        reverse("dojo-message-list"),
        data=json.dumps({"conversation": conv_id, "content": "Encore"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrftoken,
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
    )
    assert resp.status_code == 400
    assert resp.json()["conversation"] == "conversation_archived"
