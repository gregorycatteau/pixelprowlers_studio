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
from django.urls import path
from rest_framework import permissions, viewsets
from rest_framework.decorators import action, api_view, permission_classes
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

# Optional rate-limit decorator (no-op if ratelimit not installed)
try:
    from ratelimit.decorators import ratelimit as _ratelimit  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without ratelimit

    def _ratelimit(*args, **kwargs):
        def _wrap(f):
            return f

        return _wrap


# Allowed event subjects (deny-by-default)
ALLOWED_EVENT_SUBJECTS = {"intake.lead.created"}


from rest_framework.decorators import api_view, permission_classes


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@_ratelimit(key="ip", rate="30/m", block=True)
def events_gateway(request, subject: str):
    """
    Events Gateway — HMAC-signed HTTP → NATS JetStream

    Controls:
    - Subject whitelist (deny-by-default)
    - HMAC (X-Timestamp + body) in header X-Signature [sha256=HEXDIGEST or HEXDIGEST]
    - Timestamp skew window ±60s
    - Minimal rate-limit (30/min/IP) if ratelimit is available

    Env (local/dev):
      - EVENTS_HMAC_SECRET            : raw secret (string)
      - EVENTS_HMAC_SECRET_FILE       : file path to secret (takes precedence if present)
      - NATS_URL                      : e.g. nats://nats:4222
      - NATS_USER / NATS_PASS         : optional auth (e.g. dojo_user / dojo_pass)
    """
    import asyncio
    import hashlib
    import hmac
    import json
    import os
    import time
    import uuid

    # 1) Subject whitelist
    if subject not in ALLOWED_EVENT_SUBJECTS:
        return Response({"ok": False, "error": "subject_not_allowed"}, status=403)

    # 2) HMAC headers
    ts = request.META.get("HTTP_X_TIMESTAMP") or ""
    sig = request.META.get("HTTP_X_SIGNATURE") or ""
    if not ts or not sig:
        return Response({"ok": False, "error": "missing_signature"}, status=401)

    try:
        ts_int = int(ts)
    except Exception:
        return Response({"ok": False, "error": "bad_timestamp"}, status=400)

    now = int(time.time())
    if abs(now - ts_int) > 60:
        return Response({"ok": False, "error": "timestamp_skew"}, status=401)

    # 3) Load HMAC secret
    secret: bytes = (os.getenv("EVENTS_HMAC_SECRET") or "").encode("utf-8")
    if not secret:
        sec_path = os.getenv("EVENTS_HMAC_SECRET_FILE") or ""
        if sec_path and os.path.exists(sec_path):
            try:
                with open(sec_path, "rb") as f:
                    secret = f.read().strip()
            except Exception:
                secret = b""
    if not secret:
        return Response({"ok": False, "error": "hmac_secret_missing"}, status=503)

    # 4) Verify signature against payload
    body: bytes = request.body or b""
    expected_hex = hmac.new(secret, f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    cmp_sig = sig.split("=", 1)[1] if sig.startswith("sha256=") else sig
    if not hmac.compare_digest(cmp_sig, expected_hex):
        return Response({"ok": False, "error": "invalid_signature"}, status=401)

    # 5) Parse JSON payload
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return Response({"ok": False, "error": "invalid_json"}, status=400)

    # 6) Enrich and publish to NATS
    req_id = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex
    event = {
        "subject": subject,
        "data": data,
        "request_id": req_id,
        "timestamp": ts_int,
        "gateway_received_at": int(time.time()),
        "version": 1,
    }

    async def _pub() -> bool:
        try:
            import nats  # type: ignore
        except Exception:
            return False
        url = os.getenv("NATS_URL", "nats://nats:4222")
        user = os.getenv("NATS_USER") or None
        password = os.getenv("NATS_PASS") or None
        kwargs = {}
        if user or password:
            kwargs["user"] = user or ""
            kwargs["password"] = password or ""
        try:
            nc = await nats.connect(servers=[url], **kwargs)
            await nc.publish(subject, json.dumps(event).encode("utf-8"))
            await nc.flush()
            await nc.close()
            return True
        except Exception:
            return False

    ok = False
    try:
        ok = asyncio.run(_pub())
    except Exception:
        ok = False

    if not ok:
        return Response({"ok": False, "error": "nats_publish_failed"}, status=503)

    # 7) Success
    return Response({"ok": True, "request_id": req_id, "subject": subject}, status=200)


router = DefaultRouter()
router.register(r"v1/projects", ProjectViewSet, basename="project")
router.register(r"v1/users", UserViewSet, basename="user")

# This allows `include("api.views")` directly in the project urls if desired.
urlpatterns = [
    *router.urls,
    path("events/<path:subject>/", events_gateway, name="events_gateway"),
]
