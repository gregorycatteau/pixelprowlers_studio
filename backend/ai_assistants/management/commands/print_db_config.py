# -*- coding: utf-8 -*-
"""Affiche la configuration DB effective et valide la connexion."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from studio_core.dbconf import describe_db_connection


class Command(BaseCommand):
    help = "Affiche la configuration DB effective et teste SELECT version()."

    def handle(self, *args, **options):
        config = settings.DATABASES.get("default", {})
        label = describe_db_connection(config)
        redacted = dict(config)
        if "PASSWORD" in redacted:
            redacted["PASSWORD"] = "[redacted]"

        self.stdout.write(self.style.SUCCESS(f"Connexion ciblée : {label}"))
        self.stdout.write(json.dumps(redacted, indent=2, default=str))

        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
        except Exception as exc:  # pragma: no cover
            self.stderr.write(self.style.ERROR(f"❌ Connexion impossible : {exc}"))
            raise SystemExit(1) from exc

        version_short = version.split(" (", 1)[0]
        self.stdout.write(self.style.SUCCESS(f"✅ Connexion OK — {version_short}"))
