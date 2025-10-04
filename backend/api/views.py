# -*- coding: utf-8 -*-
"""
PixelProwlers Studio — DRF ViewSets (API)

Exposes:
- ProjectViewSet: CRUD scoped to the authenticated owner (admin sees all)
- UserViewSet: read-only, privacy‑aware listing of users (admin only)

Routers/URLs:
- Registers "v1/projects" and "v1/users"
- Exports `router` and `urlpatterns` so this module can be included directly:
    from django.urls import include, path
    path("", include("api.views"))

Security by design:
- Owner scoping for projects
- Minimal user surface via UserSerializer (no PII like email)
- IsAuthenticated for projects; IsAdminUser for user listing
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from .models import Project
from .serializers import ProjectSerializer, UserSerializer

# ──────────────────────────────────────────────────────────────────────────────
# Permissions
# ──────────────────────────────────────────────────────────────────────────────


class IsAuthenticatedOrReadOnlyStrict(permissions.BasePermission):
    """
    Read-only for unauthenticated requests is explicitly NOT allowed here.
    We keep this class for clarity: all actions require authentication.
    """

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsAdminUserOrOwner(permissions.BasePermission):
    """
    Allow access to admins for any object; non-admins only to their own objects.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        # Project ownership check; extend as needed for other models.
        if isinstance(obj, Project):
            return getattr(obj, "owner_id", None) == getattr(user, "pk", None)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# ViewSets
# ──────────────────────────────────────────────────────────────────────────────


class ProjectViewSet(viewsets.ModelViewSet):
    """
    CRUD for Project:
    - Admins: full access to all projects
    - Authenticated users: restricted to their own projects
    - Owner set automatically on create
    """

    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticatedOrReadOnlyStrict, IsAdminUserOrOwner)
    lookup_field = "slug"

    def get_queryset(self) -> QuerySet[Project]:
        user = self.request.user
        base = Project.objects.all().select_related("owner")
        if getattr(user, "is_superuser", False):
            return base
        if user and user.is_authenticated:
            return base.filter(owner=user)
        # No anonymous access by design
        return base.none()

    def perform_create(self, serializer: ProjectSerializer) -> None:
        # Owner from request; slug handled by serializer/model logic.
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request, *args, **kwargs) -> Response:
        """
        Convenience endpoint to list projects for the current user explicitly.
        """
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = self.get_serializer(qs, many=True)
        return Response(ser.data)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view of users.
    - Restricted to admin users to avoid leaking user data.
    - Serializer is privacy-aware (no email, no last_login exposure).
    """

    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)

    def get_queryset(self) -> QuerySet:
        User = get_user_model()
        # Keep it minimal; filter out inactive accounts by default.
        return User.objects.filter(is_active=True).order_by("id")


# ──────────────────────────────────────────────────────────────────────────────
# Router / URLs
# ──────────────────────────────────────────────────────────────────────────────

router = DefaultRouter()
router.register(r"v1/projects", ProjectViewSet, basename="project")
router.register(r"v1/users", UserViewSet, basename="user")

# This allows `include("api.views")` directly in the project urls if desired.
urlpatterns = router.urls
