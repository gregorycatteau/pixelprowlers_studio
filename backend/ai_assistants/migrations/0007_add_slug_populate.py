from __future__ import annotations

from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    AgentProfile = apps.get_model("ai_assistants", "AgentProfile")
    seen = set()
    for ap in AgentProfile.objects.all().order_by("id"):
        manifest = ap.manifest_json or {}
        ident = manifest.get("identity", {}) if isinstance(manifest, dict) else {}
        src = ident.get("slug") or ident.get("name") or ap.name or f"agent-{ap.pk}"
        base = slugify(str(src))[:50] or f"agent-{ap.pk}"

        candidate, i = base, 2
        while (
            candidate in seen
            or AgentProfile.objects.filter(slug=candidate).exclude(pk=ap.pk).exists()
        ):
            suffix = f"-{i}"
            candidate = f"{base[:50-len(suffix)]}{suffix}"
            i += 1

        ap.slug = candidate
        ap.save(update_fields=["slug"])
        seen.add(candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("ai_assistants", "0006_agentsystemcontext"),
    ]

    operations = [
        # 1) Ajout du champ (nullable) pour pouvoir le remplir
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    'ALTER TABLE "ai_assistants_agentprofile" ADD COLUMN IF NOT EXISTS "slug" varchar(50);',
                    reverse_sql='ALTER TABLE "ai_assistants_agentprofile" DROP COLUMN IF EXISTS "slug";',
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="agentprofile",
                    name="slug",
                    field=models.SlugField(max_length=50, null=True, blank=True),
                )
            ],
        ),
        # 2) Remplissage des slugs
        migrations.RunPython(populate_slugs, reverse_code=migrations.RunPython.noop),
        # 2.5) 🚿 Nettoyage d’artefacts si la migration a déjà été tentée
        migrations.RunSQL(
            'DROP INDEX IF EXISTS "ai_assistants_agentprofile_slug_af5c4d66_like";',
            reverse_sql="",
        ),
        migrations.RunSQL(
            'ALTER TABLE "ai_assistants_agentprofile" '
            'DROP CONSTRAINT IF EXISTS "ai_assistants_agentprofile_slug_key";',
            reverse_sql="",
        ),
        # 3) Resserrements : unique + non-null
        migrations.AlterField(
            model_name="agentprofile",
            name="slug",
            field=models.SlugField(max_length=50, unique=True),
        ),
    ]
