import json
import logging
from hashlib import sha256
from io import StringIO

import pytest
from ai_assistants.security import RequestNonce
from django.urls import reverse
from studio_core.logging import AgentPIIRedactionFilter


@pytest.mark.django_db
@pytest.mark.agents
def test_logs_store_message_hash_only(client_logged, csrftoken):
    url = "api_ask_agent"
    message = "Contacte user@example.com pour sk-secret-test"
    expected_hash = sha256(message.encode("utf-8")).hexdigest()
    logger = logging.getLogger("ai_assistants.ask")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(AgentPIIRedactionFilter())
    logger.addHandler(handler)

    response = client_logged.post(
        reverse(url, args=["bruce"]),
        data=json.dumps({"message": message}),
        content_type="application/json",
        HTTP_X_REQUEST_NONCE=str(RequestNonce.generate()),
        HTTP_X_CSRFTOKEN=csrftoken,
    )

    assert response.status_code == 200
    logger.removeHandler(handler)
    logged_messages = stream.getvalue()
    assert expected_hash in logged_messages
    assert "user@example.com" not in logged_messages
    assert "sk-secret-test" not in logged_messages


@pytest.mark.agents
def test_redaction_filter_masks_sensitive_patterns():
    record = logging.LogRecord(
        name="ai_assistants.ask",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Email=%s token=%s uuid=%s",
        args=("user@example.com", "sk-abc123456789", "12345678-1234-1234-1234-1234567890ab"),
        exc_info=None,
    )
    filt = AgentPIIRedactionFilter()
    assert filt.filter(record)
    message = record.getMessage()
    assert "user@example.com" not in message
    assert "sk-abc123456789" not in message
    assert "[redacted-token]" in message
    assert "[redacted-uuid]" in message
