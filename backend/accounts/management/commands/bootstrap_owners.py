# accounts/management/commands/bootstrap_owners.py
# -----------------------------------------------------------------------------
# Crée/assure l'existence du groupe 'owners' et y ajoute des utilisateurs.
# Usage:
#   poetry run python manage.py bootstrap_owners --users striker,monfils
# Env:
#   OWNERS_GROUP_NAME  (défaut: owners)
# -----------------------------------------------------------------------------
from __future__ import annotations

import os
from typing import List

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandParser


def _parse_csv(val: str | None) -> List[str]:
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


class Command(BaseCommand):
    help = "Crée le groupe owners et y ajoute les utilisateurs spécifiés."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--users",
            type=str,
            required=True,
            help="Liste CSV des usernames à ajouter au groupe owners (ex: striker,monfils)",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        group_name = os.getenv("OWNERS_GROUP_NAME", "owners")
        usernames = _parse_csv(options["users"])

        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"✔ Groupe '{group_name}' créé."))
        else:
            self.stdout.write(self.style.WARNING(f"ℹ Groupe '{group_name}' déjà existant."))

        for username in usernames:
            try:
                u = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"✖ Utilisateur introuvable: {username}"))
                continue
            u.groups.add(group)
            self.stdout.write(
                self.style.SUCCESS(f"✔ Ajouté '{username}' au groupe '{group_name}'.")
            )

        self.stdout.write(self.style.SUCCESS("✅ Bootstrap owners terminé."))
