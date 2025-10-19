from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db(transaction=True)


def test_auth_me_returns_user_data(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="striker_dev",
        email="striker_dev@example.com",
        password="test-pass-123",
        is_staff=True,
    )

    client.force_login(user)
    response = client.get("/api/auth/me/")

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    user_data = payload.get("user") or {}
    assert user_data.get("username") == "striker_dev"
    assert user_data.get("email") == "striker_dev@example.com"
    assert user_data.get("is_staff") is True
    assert user_data.get("is_superuser") is False


def test_auth_me_requires_authentication(client):
    response = client.get("/api/auth/me/")
    assert response.status_code in {401, 403}
