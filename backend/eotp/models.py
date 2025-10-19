# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class EotpChallenge(models.Model):
    """
    Challenge e-OTP (Email OTP) persistant en base.

    Exigences S1:
    - UUID PK
    - status ∈ {pending, consumed, expired, locked}
    - code_hash: Argon2id du code (pepper côté serveur)
    - tries_count, resend_count
    - timestamps: created_at, expires_at, last_sent_at
    - session_key (liaison session Django)
    - contexte minimal: UA hash (sha224), IP prefix (/24 v4, /56 v6)
    - corr_id (corrélation requête)
    - pepper_id (identifiant de la pepper active)
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONSUMED = "consumed", "Consumed"
        EXPIRED = "expired", "Expired"
        LOCKED = "locked", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eotp_challenges",
    )
    session_key = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    code_hash = models.TextField()  # Argon2id payload (inclut params/salt)
    algo = models.CharField(max_length=16, default="argon2id")
    pepper_id = models.CharField(max_length=32)

    tries_count = models.PositiveIntegerField(default=0)
    resend_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_sent_at = models.DateTimeField(null=True, blank=True)

    context_ua = models.CharField(max_length=56, null=True, blank=True)
    context_ip_prefix = models.CharField(max_length=64, null=True, blank=True)
    corr_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "eotp_challenge"
        constraints = [
            models.CheckConstraint(
                check=models.Q(expires_at__gt=models.F("created_at")),
                name="eotp_expires_after_created",
            ),
        ]
        indexes = [
            models.Index(fields=["session_key"], name="idx_eotp_session_key"),
            models.Index(fields=["status", "expires_at"], name="idx_eotp_status_expires"),
            models.Index(fields=["user", "created_at"], name="idx_eotp_user_created"),
            models.Index(fields=["created_at"], name="idx_eotp_created"),
        ]

    def __str__(self) -> str:
        return f"EotpChallenge(id={self.pk}, status={self.status}, session_key={self.session_key})"


class EotpPassphrase(models.Model):
    """
    Passphrase locale par utilisateur (optionnelle).
    - Hash Argon2id (ou fallback SHA256+pepper) stocké côté serveur
    - Aucune passphrase en clair
    - Transitions S5: set/verify via endpoints, flags PASS_ENABLE/PASS_REQUIRED
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eotp_passphrase",
        primary_key=True,
    )
    hash = models.TextField()  # payload de hachage (argon2 ou sha256+pepper)
    algo = models.CharField(max_length=16, default="argon2id")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "eotp_passphrase"
        indexes = [
            models.Index(fields=["updated_at"], name="idx_eotpp_updated"),
        ]

    def __str__(self) -> str:
        return f"EotpPassphrase(user={self.user_id}, algo={self.algo})"
