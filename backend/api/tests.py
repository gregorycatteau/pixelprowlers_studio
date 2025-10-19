# -*- coding: utf-8 -*-
"""
Basic DRF tests for Project CRUD and permissions.

Covers:
- Anonymous access is denied (401)
- Authenticated owner can create/list/retrieve/update/delete their projects
- Non-owner cannot access another user's project (404 due to queryset scoping)
- Admin can access any project
- Custom action /api/v1/projects/mine/ returns only the caller's projects
"""

from __future__ import annotations

import json
from typing import Callable, Tuple

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


@pytest.mark.django_db
def test_anonymous_cannot_access_projects_list() -> None:
    client = APIClient()
    url = reverse("project-list")  # /api/v1/projects/
    resp = client.get(url)
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.fixture()
def make_user(db) -> Callable[[str, bool], User]:
    def _mk(username: str, is_superuser: bool = False) -> User:
        u = User.objects.create_user(username=username, password="test-pass")
        if is_superuser:
            u.is_superuser = True
            u.is_staff = True
            u.save(update_fields=["is_superuser", "is_staff"])
        return u

    return _mk


def _auth_client(user: User) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _create_project(client: APIClient, name: str = "Alpha", **extra) -> Tuple[dict, str]:
    """
    Create a project via API and return (json_response, slug).
    """
    url = reverse("project-list")
    payload = {"name": name, "description": extra.get("description", ""), "status": "draft"}
    resp = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.content
    data = resp.json()
    assert "id" in data and "slug" in data and data["owner"] is not None
    return data, data["slug"]


@pytest.mark.django_db
def test_owner_can_create_project_and_is_owner(make_user) -> None:
    owner = make_user("owner1")
    client = _auth_client(owner)

    data, slug = _create_project(client, name="Site Vitrine")
    assert data["name"] == "Site Vitrine"
    assert data["owner"] == owner.pk
    assert isinstance(slug, str) and len(slug) > 0

    # retrieve by slug
    detail = reverse("project-detail", kwargs={"slug": slug})
    resp = client.get(detail)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["slug"] == slug


@pytest.mark.django_db
def test_mine_lists_only_own_projects(make_user) -> None:
    owner = make_user("owner1")
    other = make_user("other1")

    client_owner = _auth_client(owner)
    client_other = _auth_client(other)

    # Each creates a project
    _, slug_owner = _create_project(client_owner, name="Owner Project")
    _, slug_other = _create_project(client_other, name="Other Project")

    # /api/v1/projects/mine/ should return only the caller's projects
    mine_url = reverse("project-mine")
    resp_owner = client_owner.get(mine_url)
    resp_other = client_other.get(mine_url)

    assert resp_owner.status_code == status.HTTP_200_OK
    assert resp_other.status_code == status.HTTP_200_OK

    owner_slugs = {p["slug"] for p in resp_owner.json()}
    other_slugs = {p["slug"] for p in resp_other.json()}

    assert slug_owner in owner_slugs
    assert slug_other not in owner_slugs

    assert slug_other in other_slugs
    assert slug_owner not in other_slugs


@pytest.mark.django_db
def test_non_owner_cannot_access_others_project(make_user) -> None:
    owner = make_user("owner1")
    intruder = make_user("intruder")

    client_owner = _auth_client(owner)
    client_intruder = _auth_client(intruder)

    _, slug = _create_project(client_owner, name="Owner Only")

    # Intruder attempts to GET detail → 404 (scoped queryset hides it)
    detail = reverse("project-detail", kwargs={"slug": slug})
    resp = client_intruder.get(detail)
    assert resp.status_code == status.HTTP_404_NOT_FOUND

    # Intruder attempts to PATCH → also 404
    resp = client_intruder.patch(
        detail,
        data=json.dumps({"description": "hacked?"}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND

    # Intruder attempts to DELETE → 404
    resp = client_intruder.delete(detail)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_admin_can_access_any_project(make_user) -> None:
    owner = make_user("owner1")
    admin = make_user("admin1", is_superuser=True)

    client_owner = _auth_client(owner)
    client_admin = _auth_client(admin)

    _, slug = _create_project(client_owner, name="Owner Project")
    detail = reverse("project-detail", kwargs={"slug": slug})

    # Admin GET
    resp = client_admin.get(detail)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["slug"] == slug

    # Admin PATCH
    resp = client_admin.patch(
        detail,
        data=json.dumps({"status": "active"}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "active"

    # Admin DELETE
    resp = client_admin.delete(detail)
    assert resp.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_owner_update_and_delete_flow(make_user) -> None:
    owner = make_user("owner1")
    client = _auth_client(owner)

    data, slug = _create_project(client, name="Initial")
    detail = reverse("project-detail", kwargs={"slug": slug})

    # Update description and status
    resp = client.patch(
        detail,
        data=json.dumps({"description": "New desc", "status": "active"}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["description"] == "New desc"
    assert body["status"] == "active"

    # Delete
    resp = client.delete(detail)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # Ensure it's gone
    resp = client.get(detail)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
