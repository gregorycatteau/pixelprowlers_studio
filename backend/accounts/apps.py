from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """App de gestion des agents IA et de leurs scopes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Comptes & Agents IA"
