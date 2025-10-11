from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import management
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = (
        "Initialise l'environnement dev : migrations, superuser 'striker', import des agents Dojo."
    )

    SUPERUSER_USERNAME = "striker"
    SUPERUSER_EMAIL = "striker@local"
    SUPERUSER_PASSWORD = "Ide33480/(12)"

    def handle(self, *args, **options):
        self._check_database()
        self._apply_migrations()
        self._ensure_superuser()
        self._import_agents()

        self.stdout.write(
            self.style.SUCCESS(
                "✅ Env dev prêt : migrations appliquées, superuser 'striker', agents importés."
            )
        )

    def _check_database(self) -> None:
        db_settings = connection.settings_dict
        host = db_settings.get("HOST") or "localhost"
        port = db_settings.get("PORT") or "5432"

        self.stdout.write(f"🔎 Vérification PostgreSQL ({host}:{port})…")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
        except OperationalError as exc:
            self.stderr.write(
                self.style.ERROR(f"Base PostgreSQL indisponible sur {host}:{port} : {exc}")
            )
            self.stderr.write(
                self.style.ERROR(
                    "Astuce : vérifie ton service local ou exécute "
                    "'psql -h localhost -p 5432 -U <user> <db>'."
                )
            )
            raise SystemExit(1)

    def _apply_migrations(self) -> None:
        self.stdout.write("🔄 Application des migrations…")
        management.call_command("migrate", interactive=False, verbosity=1)

    def _ensure_superuser(self) -> None:
        self.stdout.write("👤 Création/mise à jour du superuser 'striker'…")
        User = get_user_model()
        superuser, created = User.objects.get_or_create(
            username=self.SUPERUSER_USERNAME,
            defaults={
                "email": self.SUPERUSER_EMAIL,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if not created:
            superuser.email = self.SUPERUSER_EMAIL
            superuser.is_staff = True
            superuser.is_superuser = True
        superuser.set_password(self.SUPERUSER_PASSWORD)
        superuser.save(update_fields=["email", "is_staff", "is_superuser", "password"])
        msg = "créé" if created else "mis à jour"
        self.stdout.write(f"   → Superuser {msg}.")

    def _import_agents(self) -> None:
        agents_dir = Path(settings.BASE_DIR) / "agents_v21"
        self.stdout.write(f"🤖 Import des agents depuis {agents_dir}…")
        management.call_command("import_agents", dir=str(agents_dir), verbosity=1)
