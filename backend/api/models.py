# -*- coding: utf-8 -*-
"""
PixelProwlers Studio — API app models

Project
- Minimal, opinionated model to support the agency dashboard (CRUD)
- Per-owner slug uniqueness, auto-slug generation from name
- Strict status lifecycle with explicit choices
- JSON metadata for light, flexible annotations (no PII)

Notes
- This model intentionally keeps business data lean for V1.
- Validation and permissions should be enforced at the serializer/viewset layer.
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify


class Project(models.Model):
    """
    A Project entity owned by a user.

    Goals:
    - Provide a simple, auditable, and secure entity for the agency dashboard.
    - Keep fields minimal for V1; prefer explicit choices over booleans.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.BigAutoField(primary_key=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        help_text="User who owns and manages this project.",
    )

    name = models.CharField(
        max_length=200,
        help_text="Human-readable name of the project.",
    )

    slug = models.SlugField(
        max_length=80,
        blank=True,
        help_text="URL-safe identifier (auto-generated from name if left blank). Unique per owner.",
    )

    description = models.TextField(
        blank=True,
        help_text="Optional description (do not store PII).",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Lifecycle status of the project.",
    )

    metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text="Lightweight structured annotations (no PII, keys/values kept minimal).",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_project"
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ("-updated_at", "id")
        indexes = [
            models.Index(fields=("owner", "slug"), name="project_owner_slug_idx"),
            models.Index(fields=("owner", "status"), name="project_owner_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "slug"),
                name="project_unique_owner_slug",
                condition=Q(slug__isnull=False) & ~Q(slug=""),
                violation_error_message="Slug must be unique for the same owner.",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name} — {self.owner}"

    # ──────────────────────────────────────────────────────────────────────────
    # Slug utilities
    # ──────────────────────────────────────────────────────────────────────────

    def _make_base_slug(self) -> str:
        base = slugify(self.name or "")[:80].strip("-")
        return base or "project"

    def _slug_exists(self, candidate: str) -> bool:
        return (
            Project.objects.filter(owner=self.owner, slug=candidate)
            .exclude(pk=getattr(self, "pk", None))
            .exists()
        )

    def _ensure_unique_slug(self, base: str) -> str:
        """
        Ensure per-owner uniqueness by appending a numeric suffix if necessary.
        """
        candidate = base
        suffix = 2
        while self._slug_exists(candidate):
            # Reserve space for suffix like "-2" within max_length
            trimmed = base[: (80 - len(str(suffix)) - 1)].rstrip("-")
            candidate = f"{trimmed}-{suffix}"
            suffix += 1
        return candidate

    def set_slug(self, value: Optional[str]) -> None:
        """
        Normalize and set slug, ensuring uniqueness within the owner's namespace.
        If value is falsy, derive slug from the name.
        """
        base = (
            slugify(value or "")[:80].strip("-")
            if (value or "").strip()
            else self._make_base_slug()
        )
        self.slug = self._ensure_unique_slug(base)

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            # Only generate when blank to avoid unexpected changes on rename.
            self.set_slug(self.slug)
        super().save(*args, **kwargs)

    # ──────────────────────────────────────────────────────────────────────────
    # URLs (optional helpers)
    # ──────────────────────────────────────────────────────────────────────────

    def get_absolute_url(self) -> str:
        # Placeholder URL pattern; wire it to your router/UI when available.
        return f"/projects/{self.slug}/"
