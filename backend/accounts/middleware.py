from __future__ import annotations

import uuid

from django.db import transaction
from django.utils.deprecation import MiddlewareMixin

from .models import AuditLog


def _client_ip(meta: dict) -> str | None:
    """
    Récupère une IP client probable en respectant X-Forwarded-For.
    """
    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return meta.get("REMOTE_ADDR")


class RequestIDAndAuditMiddleware(MiddlewareMixin):
    """
    - Injecte un X-Request-ID si absent (pour corrélation).
    - Enregistre un AuditLog par réponse (sans jamais casser la requête).
    """

    def process_request(self, request):
        rid = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = rid

    def process_response(self, request, response):
        try:
            user = getattr(request, "user", None)
            token = getattr(request, "auth", None)
            payload = getattr(token, "payload", {}) if token else {}

            with transaction.atomic():
                AuditLog.objects.create(
                    user=user if getattr(user, "is_authenticated", False) else None,
                    username=getattr(user, "username", "") or "",
                    is_agent=bool(payload.get("is_agent", False)),
                    method=getattr(request, "method", "GET")[:8],
                    path=getattr(request, "path", ""),
                    status_code=getattr(response, "status_code", 0),
                    jwt_jti=(payload or {}).get("jti", ""),
                    jwt_scopes=list((payload or {}).get("scopes", []) or []),
                    ip=_client_ip(getattr(request, "META", {})),
                    user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:1024],
                )
        except Exception:
            pass  # L'audit ne doit jamais impacter la réponse

        response["X-Request-ID"] = getattr(request, "request_id", "")
        return response
