#!/usr/bin/env python
"""
Bootstrap minimal data set for Playwright E2E runs.

This script is idempotent and can be invoked multiple times before executing
tests. It ensures:
  - a superuser with predictable credentials exists
  - a Dojo agent is available for conversation flows
  - previous conversations/messages are cleared to provide a clean slate
"""

from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studio_core.settings.dev")
    os.environ.setdefault("APP_ENV", "dev")

    import django

    django.setup()

    from ai_assistants.models import Conversation, ConversationMessage, DojoAgent
    from django.contrib.auth import get_user_model
    from django.core.cache import cache

    username = os.getenv("E2E_SUPERUSER", "dojo_admin")
    password = os.getenv("E2E_SUPERUSER_PASSWORD", "dojo_admin_pass")
    email = os.getenv("E2E_SUPERUSER_EMAIL", "dojo_admin@example.com")

    User = get_user_model()

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
            "first_name": "Dojo",
            "last_name": "Admin",
        },
    )
    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
    else:
        # Always reset password to guarantee tests can authenticate.
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["password", "is_staff", "is_superuser"])

    # Minimal Dojo agent catalogue
    DojoAgent.objects.update_or_create(
        slug="claire",
        defaults={
            "title": "Claire",
            "description": "Agent de confiance (E2E)",
            "capabilities": {"modes": ["echo"]},
            "is_active": True,
        },
    )

    # Clean previous conversations/messages to avoid bleed between test runs.
    ConversationMessage.objects.all().delete()
    Conversation.objects.all().delete()

    # Drop any cached flags (gate/session)
    cache.clear()

    print("E2E bootstrap complete for user:", username)


if __name__ == "__main__":
    main()
