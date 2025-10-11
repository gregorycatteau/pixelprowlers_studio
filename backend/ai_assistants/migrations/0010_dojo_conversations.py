from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_assistants", "0009_agentrun_agenttoolcall_dailybudget_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DojoAgent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("slug", models.SlugField(unique=True)),
                ("title", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True, default="")),
                ("capabilities", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Agent Dojo",
                "verbose_name_plural": "Agents Dojo",
                "ordering": ["slug"],
            },
        ),
        migrations.CreateModel(
            name="Conversation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=160)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Ouverte"),
                            ("closed", "Fermée"),
                            ("archived", "Archivée"),
                        ],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="conversations",
                        to="ai_assistants.dojoagent",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dojo_conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Conversation Dojo",
                "verbose_name_plural": "Conversations Dojo",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ConversationAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("action", models.CharField(max_length=64)),
                ("object_type", models.CharField(max_length=64)),
                ("object_id", models.CharField(max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Audit conversation",
                "verbose_name_plural": "Audits conversation",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ConversationMessage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("user", "Admin"), ("agent", "Agent"), ("system", "Système")],
                        max_length=16,
                    ),
                ),
                ("content", models.TextField()),
                ("tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="ai_assistants.conversation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Message de conversation",
                "verbose_name_plural": "Messages de conversation",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["creator", "created_at"], name="dojo_conv_creator_idx"),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["agent", "status"], name="dojo_conv_agent_status_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationmessage",
            index=models.Index(
                fields=["conversation", "created_at"], name="dojo_msg_conv_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="conversationauditlog",
            index=models.Index(fields=["action", "created_at"], name="dojo_audit_action_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationauditlog",
            index=models.Index(fields=["object_type", "object_id"], name="dojo_audit_object_idx"),
        ),
    ]
