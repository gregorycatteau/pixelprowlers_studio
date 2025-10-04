# -*- coding: utf-8 -*-
"""
API app package for PixelProwlers Studio.

This Django app exposes a REST API (DRF) for core entities and documentation:
- OpenAPI schema via drf-spectacular (configured in project urls and settings)
- ViewSets and routers for versioned endpoints (e.g., users/, projects/)
- Serializers with strict validation
- Permissions aligned with RACI/security posture

Expected sibling modules (created in subsequent commits):
- apps.py        → AppConfig (ApiConfig)
- models.py      → e.g., Project model (CRUD minimal)
- serializers.py → DRF serializers for entities
- views.py       → DRF ViewSets / endpoints
- urls.py        → DRF router with registered ViewSets

Note:
- Django 5+ does not require default_app_config; it’s harmless for back-compat.
- Settings should include:
    INSTALLED_APPS += ["api", "rest_framework", "drf_spectacular"]
    REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"
"""

from __future__ import annotations

from typing import Final

__all__ = [
    # Informational exports (modules will be provided by sibling files)
    "APIS_APP_LABEL",
    "__version__",
]

# App label used consistently across the package (migrations, routing context, etc.)
APIS_APP_LABEL: Final[str] = "api"

# Package version (bump when API surface or behavior changes)
__version__: Final[str] = "0.1.0"

# Backward-compat directive (ignored in modern Django, safe otherwise)
default_app_config: Final[str] = "api.apps.ApiConfig"
