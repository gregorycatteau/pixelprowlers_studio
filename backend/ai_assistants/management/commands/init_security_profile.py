# ai_assistants/management/commands/init_security_profile.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from ai_assistants.models import UserSecurityProfile
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Initialise/Met à jour le UserSecurityProfile d’un utilisateur."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Nom d’utilisateur")
        parser.add_argument("--hue", type=int, default=202, help="Teinte HSL attendue (0..359)")
        parser.add_argument("--tol", type=int, default=8, help="Tolérance (degrés)")
        parser.add_argument(
            "--order", type=str, default="1,4,7,3", help="Séquence indices (ex: 1,4,7,3)"
        )

    def handle(self, *args, **opts):
        User = get_user_model()
        username = opts["username"]
        hue = int(opts["hue"])
        tol = int(opts["tol"])
        order_str = opts["order"]
        try:
            order = [int(x.strip()) for x in order_str.split(",")]
            if len(order) != 4:
                raise ValueError
        except Exception:
            raise CommandError(
                "Param --order doit contenir exactement 4 entiers séparés par des virgules."
            )

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"Utilisateur '{username}' introuvable.")

        usp, _ = UserSecurityProfile.objects.get_or_create(user=user)
        usp.secret_hue = max(0, min(359, hue))
        usp.hue_tolerance = max(0, min(60, tol))
        usp.set_emoji_secret(order)
        usp.clear_failures()
        usp.sandbox_until = None
        usp.save()

        self.stdout.write(self.style.SUCCESS(f"Profil sécu mis à jour pour {username}."))
