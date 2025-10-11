"""
Utilities related to additional security checks for AI assistant endpoints.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse

try:  # pragma: no cover - optional dependency path
    import redis  # type: ignore
except Exception:  # pragma: no cover - fallback when redis is absent
    redis = None

logger = logging.getLogger(__name__)

_NONCE_SALT = "ai_assistants.ask_agent_nonce"
_NONCE_TTL_SECONDS = int(getattr(settings, "REQUEST_NONCE_TTL_SECONDS", 60))
_NONCE_CACHE_PREFIX = "ask-agent-nonce"


class NonceError(Exception):
    """Base class for nonce validation errors."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _nonce_cache_key(payload: str, user_id: int | None) -> str:
    return f"{_NONCE_CACHE_PREFIX}:{user_id or 'anon'}:{payload}"


def _env_redis_url() -> str | None:
    # Priority: explicit setting > env var > generic REDIS_URL
    return (
        getattr(settings, "REQUEST_NONCE_REDIS_URL", None)
        or os.getenv("REQUEST_NONCE_REDIS_URL")
        or getattr(settings, "REDIS_URL", None)
        or os.getenv("REDIS_URL")
    )


def _max_connections() -> int:
    try:
        return int(os.getenv("REQUEST_NONCE_REDIS_MAX_CONNECTIONS", "16"))
    except ValueError:
        return 16


@lru_cache(maxsize=1)
def _build_redis_pool():
    if redis is None:
        return None
    url = _env_redis_url()
    if not url:
        return None
    try:
        return redis.ConnectionPool.from_url(
            url,
            decode_responses=True,
            max_connections=_max_connections(),
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("RequestNonce redis pool init failed: %s", exc)
        return None


@lru_cache(maxsize=1)
def _build_redis_client():
    pool = _build_redis_pool()
    if pool is None or redis is None:
        return None
    try:
        return redis.Redis(connection_pool=pool, decode_responses=True, health_check_interval=30)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("RequestNonce redis init failed: %s", exc)
        return None


class _CacheNonceStore:
    """Fallback nonce store relying on Django cache."""

    def register(self, payload: str, user_id: int | None) -> None:
        cache_key = _nonce_cache_key(payload, user_id)
        cache.set(cache_key, True, timeout=_NONCE_TTL_SECONDS)

    def consume(self, payload: str, user_id: int | None) -> None:
        cache_key = _nonce_cache_key(payload, user_id)
        removed = cache.delete(cache_key)
        if not removed and user_id is not None:
            removed = cache.delete(_nonce_cache_key(payload, None))
        if not removed:
            raise NonceError("nonce_replay")


class _RedisNonceStore:
    """Nonce store backed by Redis with NX semantics."""

    def __init__(self, client):
        self.client = client
        self._disabled = False

    def _fallback(self) -> _CacheNonceStore:
        self._disabled = True
        return _cache_store()

    def register(self, payload: str, user_id: int | None) -> None:
        if self._disabled:
            _cache_store().register(payload, user_id)
            return

        cache_key = _nonce_cache_key(payload, user_id)
        try:
            stored = self.client.set(cache_key, "1", ex=_NONCE_TTL_SECONDS, nx=True)
        except Exception as exc:  # pragma: no cover - network/redis failures
            logger.warning("RequestNonce redis register error (%s). Falling back to cache.", exc)
            self._fallback().register(payload, user_id)
            return

        if not stored:
            # If the key already exists we overwrite TTL to keep freshness.
            try:
                self.client.expire(cache_key, _NONCE_TTL_SECONDS)
            except Exception:
                pass

    def consume(self, payload: str, user_id: int | None) -> None:
        if self._disabled:
            _cache_store().consume(payload, user_id)
            return

        cache_key = _nonce_cache_key(payload, user_id)
        try:
            removed = self.client.delete(cache_key)
        except Exception as exc:  # pragma: no cover - network/redis failures
            logger.warning("RequestNonce redis consume error (%s). Falling back to cache.", exc)
            self._fallback().consume(payload, user_id)
            return

        if not removed and user_id is not None:
            try:
                removed = self.client.delete(_nonce_cache_key(payload, None))
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "RequestNonce redis consume fallback error (%s). Falling back to cache.",
                    exc,
                )
                self._fallback().consume(payload, user_id)
                return

        if not removed:
            raise NonceError("nonce_replay")


@lru_cache(maxsize=1)
def _cache_store() -> _CacheNonceStore:
    return _CacheNonceStore()


@lru_cache(maxsize=1)
def _nonce_store():
    client = _build_redis_client()
    if client is not None:
        return _RedisNonceStore(client)
    return _cache_store()


@dataclass(frozen=True)
class RequestNonce:
    """
    Handles generation and validation of short-lived request nonces.

    The nonce is composed of a random payload signed and timestamped.
    Each nonce can only be used once (tracked via Redis/cache) and
    expires after `_NONCE_TTL_SECONDS`.
    """

    value: str

    signer = signing.TimestampSigner(salt=_NONCE_SALT)
    ttl_seconds = _NONCE_TTL_SECONDS

    @classmethod
    def generate(cls, user_id: Optional[int] = None) -> "RequestNonce":
        payload = secrets.token_urlsafe(24)
        signed = cls.signer.sign(payload)
        _nonce_store().register(payload, user_id)
        return cls(signed)

    @classmethod
    def validate(cls, raw_nonce: str, user_id: int | None = None) -> None:
        if not raw_nonce:
            raise NonceError("nonce_missing")

        try:
            payload = cls.signer.unsign(raw_nonce, max_age=_NONCE_TTL_SECONDS)
        except signing.SignatureExpired as exc:
            raise NonceError("nonce_expired") from exc
        except signing.BadSignature as exc:
            raise NonceError("nonce_invalid") from exc

        _nonce_store().consume(payload, user_id)

    def __str__(self) -> str:
        return self.value


def issue_chained_nonce(response: HttpResponse, user_id: Optional[int] = None) -> str:
    """
    Attaches a freshly generated nonce to the HTTP response so the client can
    chain subsequent mutating calls without round-tripping to /api/auth/nonce/.
    """
    nonce = str(RequestNonce.generate(user_id=user_id))
    response["X-New-Request-Nonce"] = nonce
    return nonce
