"""
Logging utilities for PixelProwlers studio.

Contains filters that remove potentially sensitive information from log
messages emitted by security-critical components (agents API).
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, MutableMapping, Optional

EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
TOKEN_RE = re.compile(r"(sk-[a-zA-Z0-9]{10,})")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

_REQUEST_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "ppw_request_context", default=None
)


def redact_text(value: Any) -> str:
    """
    Replace likely sensitive substrings (emails, tokens, UUIDs) from log output.
    """
    text = str(value)

    text = EMAIL_RE.sub(r"\1@[redacted]", text)
    text = TOKEN_RE.sub("[redacted-token]", text)
    text = UUID_RE.sub("[redacted-uuid]", text)
    return text


class AgentPIIRedactionFilter(logging.Filter):
    """
    Logging filter applied to agent-related loggers in order to prevent PII leaks.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True

        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def request_context() -> MutableMapping[str, Any]:
    """
    Fetch (or initialise) the per-request logging context.
    """
    ctx = _REQUEST_CONTEXT.get()
    if ctx is None:
        ctx = {}
        _REQUEST_CONTEXT.set(ctx)
    return ctx


def clear_request_context() -> None:
    """Reset the per-request logging context."""
    _REQUEST_CONTEXT.set({})


def update_request_context(values: Mapping[str, Any]) -> None:
    """
    Merge `values` into the request context, dropping keys with falsy values.
    """
    ctx = request_context()
    for key, value in values.items():
        if value is None or value == "":
            ctx.pop(key, None)
        else:
            ctx[key] = value


class RequestContextFilter(logging.Filter):
    """
    Inject the request context into each log record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = request_context().copy()
        for key, value in ctx.items():
            setattr(record, key, value)
        return True


def _base_log_payload(record: logging.LogRecord) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        "level": record.levelname.lower(),
        "logger": record.name,
        "message": record.getMessage(),
    }

    for attr in (
        "request_id",
        "method",
        "path",
        "status",
        "status_code",
        "duration_ms",
        "user_id",
        "username",
        "ip",
        "user_agent",
        "referer",
    ):
        value = getattr(record, attr, None)
        if value not in (None, ""):
            key = attr if attr != "status_code" else "status"
            payload[key] = value

    if record.exc_info:
        try:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else None
        except Exception:
            exc_type = None
        payload["exception"] = {
            "type": exc_type,
            "message": str(record.exc_info[1]) if record.exc_info else "",
            "stack": (
                logging.Formatter().formatException(record.exc_info) if record.exc_info else ""
            ),
        }
    return payload


class JsonLogFormatter(logging.Formatter):
    """
    Emit structured JSON logs with request contextual information when available.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = _base_log_payload(record)
        return json.dumps(payload, separators=(",", ":"))
