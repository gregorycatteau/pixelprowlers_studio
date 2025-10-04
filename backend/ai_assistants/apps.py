# backend/ai_assistants/apps.py
# -*- coding: utf-8 -*-
from django.apps import AppConfig


class AiAssistantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ai_assistants"  # ⬅️ surtout pas "backend.ai_assistants"
    label = "ai_assistants"
    verbose_name = "AI Assistants"
