import json

import pytest
from ai_assistants.security import RequestNonce
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.agents
def test_ask_agent_within_throttle_limit(client_logged, csrftoken):
    url = reverse("api_ask_agent", args=["bruce"])
    responses = []
    for _ in range(3):
        nonce = str(RequestNonce.generate())
        resp = client_logged.post(
            url,
            data=json.dumps({"message": "ping"}),
            content_type="application/json",
            HTTP_X_REQUEST_NONCE=nonce,
            HTTP_X_CSRFTOKEN=csrftoken,
        )
        responses.append(resp.status_code)
    assert all(status == 200 for status in responses)


@pytest.mark.django_db
@pytest.mark.agents
def test_ask_agent_throttle_blocks_after_limit(client_logged, csrftoken):
    url = reverse("api_ask_agent", args=["bruce"])
    status_codes = []
    for _ in range(6):
        nonce = str(RequestNonce.generate())
        resp = client_logged.post(
            url,
            data=json.dumps({"message": "flood"}),
            content_type="application/json",
            HTTP_X_REQUEST_NONCE=nonce,
            HTTP_X_CSRFTOKEN=csrftoken,
        )
        status_codes.append(resp.status_code)

    assert status_codes[-1] == 429
    assert status_codes.count(200) == 5
