from __future__ import annotations

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """
    AppConfig for the PixelProwlers Studio REST API (DRF-based).

    Responsibilities:
    - Host ViewSets/routers for versioned endpoints (e.g., users/, projects/).
    - Integrate with drf-spectacular for OpenAPI schema generation.
    - Provide a home for serializers, permissions, and API-related signals.

    Notes:
    - Ensure INSTALLED_APPS includes "api", "rest_framework", and "drf_spectacular".
    - REST_FRAMEWORK should declare DEFAULT_SCHEMA_CLASS to drf-spectacular.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "PixelProwlers API"

    def ready(self) -> None:  # noqa: D401
        """
        Hook for app initialization (import signals or validators when needed).
        Kept minimal in v1.
        """
        # from . import signals  # noqa: F401  # Enable when signals are added
        return
