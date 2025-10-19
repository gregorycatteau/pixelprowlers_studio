# -*- coding: utf-8 -*-
from __future__ import annotations

import hmac
import os
from typing import Optional

from django.conf import settings

from .models import EotpPassphrase


# Flags/peppers — runtime-read for tests/ops
def _flag_enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


PASS_ENABLE = _flag_enabled("PASS_ENABLE", "1")
PASS_REQUIRED = _flag_enabled("PASS_REQUIRED", "0")
PASS_PEPPER = (
    os.getenv("PASS_PEPPER") or os.getenv("EOTP_PEPPER") or getattr(settings, "SECRET_KEY", "")
)

try:
    from argon2 import PasswordHasher  # type: ignore

    _PWH = PasswordHasher()
    _HAS_ARGON2 = True
except Exception:  # pragma: no cover
    _PWH = None
    _HAS_ARGON2 = False


def _hash_payload(plaintext: str) -> str:
    """
    Hash la passphrase: Argon2id + pepper si dispo, sinon SHA256(plaintext||pepper).
    Jamais retourner la passphrase en clair.
    """
    payload = f"{plaintext}:{PASS_PEPPER}"
    if _HAS_ARGON2 and _PWH is not None:
        try:
            return _PWH.hash(payload)
        except Exception:
            pass
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_payload(stored_hash: str, plaintext: str) -> bool:
    payload = f"{plaintext}:{PASS_PEPPER}"
    if _HAS_ARGON2 and _PWH is not None:
        try:
            return _PWH.verify(stored_hash, payload)
        except Exception:
            return False
    import hashlib

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored_hash, digest)


def user_has_passphrase(user_id: int) -> bool:
    """
    True si une passphrase est définie pour cet utilisateur.
    """
    try:
        return EotpPassphrase.objects.filter(user_id=user_id).exists()
    except Exception:
        return False


def set_passphrase_for_user(user_id: int, plaintext: str) -> bool:
    """
    Crée/Met à jour la passphrase pour l'utilisateur (hashée).
    Retourne True si succès.
    """
    if not PASS_ENABLE:
        return False
    if not user_id or not plaintext or not isinstance(plaintext, str):
        return False
    try:
        hashed = _hash_payload(plaintext)
        obj, _created = EotpPassphrase.objects.update_or_create(
            user_id=user_id,
            defaults={"hash": hashed, "algo": "argon2id" if _HAS_ARGON2 else "sha256"},
        )
        return True
    except Exception:
        return False


def verify_passphrase_for_user(user_id: int, plaintext: str) -> bool:
    """
    Vérifie la passphrase pour l'utilisateur.
    """
    if not PASS_ENABLE:
        return False
    if not user_id or not plaintext or not isinstance(plaintext, str):
        return False
    try:
        obj = EotpPassphrase.objects.filter(user_id=user_id).only("hash", "algo").first()
        if not obj:
            return False
        return _verify_payload(obj.hash, plaintext)
    except Exception:
        return False
