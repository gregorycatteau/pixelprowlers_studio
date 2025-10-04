# -*- coding: utf-8 -*-
"""
Honeypot /admin :
- Incrémente un compteur par (IP, UA) avec TTL.
- Loggue en INFO/WARNING/ERROR selon le seuil.
- Aucune donnée sensible stockée.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Tuple

from django.core.cache import cache
from django.http import HttpRequest

logger = logging.getLogger("security.honeypot")

TTL_SECONDS = 24 * 3600  # fenêtre d'observation
ALERT_THRESHOLD = 5  # au-delà → log ERROR


def _client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "-")


def _fingerprint(ip: str, ua: str) -> Tuple[str, str]:
    """Construit des clés cache courtes & stables pour (IP, UA)."""
    ua_hash = hashlib.sha256(ua.encode("utf-8")).hexdigest()[:12]
    key = f"honeypot:{ip}:{ua_hash}"
    return key, ua_hash


def log_honeypot_hit(request: HttpRequest) -> int:
    """
    Incrémente le compteur et loggue l'événement.
    :return: nouveau compteur (hits sur la fenêtre TTL)
    """
    ip = _client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "-")
    referer = request.META.get("HTTP_REFERER", "-")
    path = request.path

    key, ua_hash = _fingerprint(ip, ua)

    # incr robuste (LocMem/Redis) — crée si absent
    try:
        count = cache.incr(key)
    except Exception:
        cache.set(key, 1, TTL_SECONDS)
        count = 1
    else:
        # assure un TTL si backend ne le prolonge pas
        cache.touch(key, TTL_SECONDS)

    # Logging structuré
    msg = f"Honeypot /admin touché (#{count}) — ip={ip} ua_hash={ua_hash} path={path}"
    extra = {
        "ip": ip,
        "ua_hash": ua_hash,
        "ua": ua,
        "path": path,
        "referer": referer,
        "count": count,
    }

    if count >= ALERT_THRESHOLD:
        logger.error(msg, extra=extra)
    elif count >= 2:
        logger.warning(msg, extra=extra)
    else:
        logger.info(msg, extra=extra)

    return count
