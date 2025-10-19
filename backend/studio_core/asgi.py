# -*- coding: utf-8 -*-
"""
ASGI + MCP (SSE) pour PixelProwlers.
"""
import os
import sys

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "studio_core.settings.dev")
)

django.setup()
django_http_app = get_asgi_application()

MCP_ENABLED = os.getenv("DJANGO_MCP_ENABLED", "true").lower() not in ("0", "false", "no")
MCP_BASE_PATH = os.getenv("DJANGO_MCP_PATH_PREFIX", "/mcp").rstrip("/") or "/mcp"

if not MCP_ENABLED:
    print(
        f"[ASGI] MCP disabled via DJANGO_MCP_ENABLED; SSE not mounted. Base path would be {MCP_BASE_PATH}/sse",
        file=sys.stderr,
    )

application = django_http_app
if MCP_ENABLED:
    try:
        from django_mcp import mount_mcp_server  # fournit /mcp/sse + /mcp/messages

        application = mount_mcp_server(django_http_app=django_http_app, mcp_base_path=MCP_BASE_PATH)
    except Exception as exc:
        print(f"[ASGI] MCP mount failed: {exc}", file=sys.stderr)
        application = django_http_app
