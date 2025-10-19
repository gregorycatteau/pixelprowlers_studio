# -*- coding: utf-8 -*-
# Migration: add timestamps to AgentProfile with safe defaults for existing rows

from __future__ import annotations

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_assistants", "0007_add_slug_populate"),
    ]

    operations = [
        # Add created_at with auto_now_add=True.
        # Provide a one-off default (timezone.now) for existing rows, then drop the default for future inserts.
        migrations.AddField(
            model_name="agentprofile",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                editable=False,
            ),
            preserve_default=False,
        ),
    ]
