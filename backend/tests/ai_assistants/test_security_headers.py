import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.agents
def test_security_headers_present(client_logged):
    response = client_logged.get(reverse("api_list_agents"))
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert headers.get("Permissions-Policy") is not None
    assert headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert headers.get("Cross-Origin-Embedder-Policy") == "same-origin"
