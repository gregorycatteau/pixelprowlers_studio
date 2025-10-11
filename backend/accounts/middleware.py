from __future__ import annotations

import logging
import time
import uuid

from django.db import transaction
from django.utils.deprecation import MiddlewareMixin
from studio_core.logging import clear_request_context, update_request_context

from .models import AuditLog

try:
    import sentry_sdk
except Exception:  # pragma: no cover - sentry optional
    sentry_sdk = None


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

    request_logger = logging.getLogger("studio_core.request")

    def process_request(self, request):
        clear_request_context()
        rid = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = rid
        request._pp_request_started_at = time.perf_counter()

        update_request_context(
            {
                "request_id": rid,
                "method": getattr(request, "method", "").upper(),
                "path": getattr(request, "path", ""),
                "ip": _client_ip(getattr(request, "META", {})),
                "user_agent": (request.META.get("HTTP_USER_AGENT", "") or "")[:512],
            }
        )

        user = getattr(request, "user", None)
        if sentry_sdk:
            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("request_id", rid)
                scope.set_tag("http.method", getattr(request, "method", "GET"))
                scope.set_tag("http.path", getattr(request, "path", ""))
                scope.set_user(
                    {"id": getattr(user, "pk", None)}
                    if getattr(user, "is_authenticated", False)
                    else None
                )
        if getattr(user, "is_authenticated", False):
            update_request_context(
                {
                    "user_id": getattr(user, "pk", None),
                    "username": getattr(user, "username", "") or "",
                }
            )

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
                    request_id=getattr(request, "request_id", ""),
                    jwt_jti=(payload or {}).get("jti", ""),
                    jwt_scopes=list((payload or {}).get("scopes", []) or []),
                    ip=_client_ip(getattr(request, "META", {})),
                    user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:1024],
                )
        except Exception:
            pass  # L'audit ne doit jamais impacter la réponse

        status_code = getattr(response, "status_code", 0)
        duration_ms = None
        try:
            started = getattr(request, "_pp_request_started_at", None)
            if started is not None:
                duration_ms = (time.perf_counter() - started) * 1000.0
        except Exception:
            duration_ms = None

        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            update_request_context(
                {
                    "user_id": getattr(user, "pk", None),
                    "username": getattr(user, "username", "") or "",
                }
            )

        update_request_context(
            {
                "status": status_code,
                "duration_ms": None if duration_ms is None else round(duration_ms, 2),
            }
        )

        if sentry_sdk:
            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("http.status_code", status_code)
                if duration_ms is not None:
                    scope.set_extra("duration_ms", round(duration_ms, 2))

        try:
            self.request_logger.info(
                "request.completed",
                extra={
                    "status": status_code,
                    "duration_ms": None if duration_ms is None else round(duration_ms, 2),
                },
            )
        except Exception:
            pass
        finally:
            clear_request_context()

        response["X-Request-ID"] = getattr(request, "request_id", "")
        return response

    def process_exception(self, request, exception):
        update_request_context({"status": 500})
        try:
            self.request_logger.error("request.exception", exc_info=exception)
        except Exception:
            pass
        finally:
            clear_request_context()
        return None
