# backend/ai_assistants/management/commands/cleanup_ops_admin.py
# -*- coding: utf-8 -*-
"""
Command that disables or removes the temporary `ops_admin` superuser.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Désactive l'utilisateur temporaire ops_admin (ou reset password)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Supprime complètement l'utilisateur au lieu de le désactiver.",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username="ops_admin")
        except user_model.DoesNotExist:
            self.stdout.write(self.style.SUCCESS("✅ Aucun utilisateur ops_admin détecté."))
            return

        if options.get("delete"):
            user.delete()
            self.stdout.write(self.style.SUCCESS("🧹 Utilisateur ops_admin supprimé."))
            return

        user.is_active = False
        user.set_password(secrets.token_urlsafe(32))
        user.save(update_fields=["is_active", "password"])
        self.stdout.write(
            self.style.SUCCESS("🔒 Utilisateur ops_admin désactivé et mot de passe réinitialisé.")
        )
