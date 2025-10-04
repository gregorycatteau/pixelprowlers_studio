# -*- coding: utf-8 -*-
"""
PixelProwlers Studio — DRF serializers for API app.

Includes:
- ProjectSerializer: CRUD serializer for the Project model, with opinionated
  defaults (owner from request, safe slugging, basic metadata validation).
- UserSerializer (placeholder): minimal, privacy‑aware projection of the
  Django user model for listing/”whoami” contexts (no email/PII).

Notes
- Keep business data lean for V1; prefer explicit validation and read‑only
  where applicable.
- Respect “security by design”: avoid leaking PII, avoid mass‑assignment
  of privileged fields, normalize slugs and check per‑owner uniqueness.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils.text import slugify
from rest_framework import serializers

from .models import Project

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _normalize_slug(value: Optional[str]) -> str:
    """
    Slugify input with a conservative limit.
    Empty/falsy strings return an empty slug (caller decides fallback).
    """
    if not value:
        return ""
    return slugify(value)[:80].strip("-")


def _validate_metadata_shape(meta: Any) -> Dict[str, Any]:
    """
    Basic “shape” validation for JSON metadata to keep it lean and avoid PII.
    Rules (opinionated for V1):
    - Must be a dict with at most ~25 keys (avoid dumping large objects)
    - Keys must be strings with max length 64
    - Values can be str/bool/int/float or small dict/list (1 level) with similar constraints
    - No obvious PII-like keys (e.g., “password”, “ssn”, “credit_card”, “token”)
    """
    if meta in (None, ""):
        return {}

    if not isinstance(meta, dict):
        raise serializers.ValidationError("metadata must be an object")

    if len(meta) > 25:
        raise serializers.ValidationError("metadata has too many top-level keys (max 25)")

    banned_keys = {"password", "pass", "secret", "token", "api_key", "apikey", "ssn", "credit_card"}

    def _ok_scalar(v: Any) -> bool:
        return isinstance(v, (str, bool, int, float)) or v is None

    def _ok_key(k: Any) -> bool:
        return isinstance(k, str) and 1 <= len(k) <= 64 and k.lower() not in banned_keys

    for k, v in meta.items():
        if not _ok_key(k):
            raise serializers.ValidationError(
                f"metadata key invalid or potentially sensitive: {k!r}"
            )
        if _ok_scalar(v):
            continue
        if isinstance(v, dict):
            if len(v) > 20:
                raise serializers.ValidationError(f"metadata.{k}: nested object too large")
            for nk, nv in v.items():
                if not _ok_key(nk) or not _ok_scalar(nv):
                    raise serializers.ValidationError(f"metadata.{k}: invalid nested key/value")
            continue
        if isinstance(v, list):
            if len(v) > 50:
                raise serializers.ValidationError(f"metadata.{k}: list too large")
            if not all(_ok_scalar(x) for x in v[:50]):
                raise serializers.ValidationError(f"metadata.{k}: list contains unsupported values")
            continue
        raise serializers.ValidationError(f"metadata.{k}: unsupported value type")

    return meta


# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────


class ProjectSerializer(serializers.ModelSerializer):
    """
    Opinionated serializer for Project with:
    - owner set from request.user at creation (read-only from API)
    - safe slug handling (optional input; unique per owner)
    - basic metadata validation
    """

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    slug = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="URL-safe identifier; if omitted/blank, it will be generated from name.",
    )
    status = serializers.ChoiceField(choices=Project.Status.choices, default=Project.Status.DRAFT)

    class Meta:
        model = Project
        fields = (
            "id",
            "owner",
            "name",
            "slug",
            "description",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "owner", "created_at", "updated_at")

    # ── Field-level validations ────────────────────────────────────────────────

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("name is required")
        if len(value) > 200:
            raise serializers.ValidationError("name is too long (max 200)")
        return value

    def validate_slug(self, value: Optional[str]) -> str:
        # Normalize and allow empty; we’ll generate on create/update if needed.
        norm = _normalize_slug(value)
        if len(norm) > 80:
            raise serializers.ValidationError("slug too long (max 80)")
        return norm

    def validate_metadata(self, value: Any) -> Dict[str, Any]:
        return _validate_metadata_shape(value)

    # ── Object-level validations ──────────────────────────────────────────────

    def _owner_from_request(self):
        req = self.context.get("request")
        user = getattr(req, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def _ensure_unique_per_owner(self, owner, slug_value: str, pk: Optional[int] = None) -> None:
        if not slug_value:
            return
        qs = Project.objects.filter(owner=owner, slug=slug_value)
        if pk:
            qs = qs.exclude(pk=pk)
        if qs.exists():
            raise serializers.ValidationError({"slug": "slug must be unique for the same owner"})

    # ── Create / Update ───────────────────────────────────────────────────────

    def create(self, validated_data: Dict[str, Any]) -> Project:
        owner = self._owner_from_request()
        if owner is None:
            raise serializers.ValidationError("authenticated owner required to create a project")

        # Pop slug; generate if blank
        raw_slug = validated_data.pop("slug", "")
        name = validated_data.get("name") or ""
        proj = Project(owner=owner, **validated_data)

        try:
            # Generate slug either from input or from name
            if raw_slug:
                proj.set_slug(raw_slug)
            else:
                proj.set_slug(name)
            # Check uniqueness per owner
            self._ensure_unique_per_owner(owner, proj.slug)
            proj.full_clean(exclude=["slug"])  # keep model validations
            proj.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        return proj

    def update(self, instance: Project, validated_data: Dict[str, Any]) -> Project:
        # Owner cannot be changed via API
        validated_data.pop("owner", None)

        # Handle slug update (optional); when blank, regenerate from (new) name
        new_slug = validated_data.pop("slug", None)
        new_name = validated_data.get("name", instance.name)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)

        if new_slug is not None:
            norm = _normalize_slug(new_slug)
            if norm:
                instance.set_slug(norm)
            else:
                # Recompute from current/new name
                instance.set_slug(new_name)

        # Uniqueness check per owner if slug is set
        self._ensure_unique_per_owner(instance.owner, instance.slug, pk=instance.pk)

        try:
            instance.full_clean(exclude=["slug"])
            instance.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)
        return instance


class UserSerializer(serializers.ModelSerializer):
    """
    Placeholder, privacy‑aware serializer for the Django user model.

    Intentionally omits fields like email/last_login to minimize PII exposure.
    Suitable for:
    - whoami endpoints
    - listing owners on minimal UIs

    Extend later with dedicated endpoints/permissions as needed.
    """

    display_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "is_active",
            "is_superuser",
            "display_name",
        )
        read_only_fields = ("id", "is_active", "is_superuser", "display_name")

    def get_display_name(self, obj) -> str:  # noqa: D401
        """
        Build a light, non‑PII display name (fallbacks on username).
        """
        first = (obj.first_name or "").strip()
        last = (obj.last_name or "").strip()
        if first or last:
            # Avoid leaking full names in privacy‑sensitive contexts later if needed
            return f"{first} {last}".strip()
        return obj.username or f"user-{obj.pk}"
