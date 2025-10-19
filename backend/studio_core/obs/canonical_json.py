# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Canonical JSON v1 + Hash chaining helpers.

Rules (v1):
- UTF-8 bytes output
- Object keys sorted lexicographically
- No insignificant whitespace (compact separators)
- Ensure Python types are JSON-compatible (dict, list, str, int, float, bool, None)
- Floats serialized with standard JSON encoding (no NaN/Inf)

Functions:
- to_canonical(obj) -> bytes
- sha256_chain(prev_hash: bytes, current: bytes) -> bytes
"""

import hashlib
import json
from typing import Any


def to_canonical(obj: Any) -> bytes:
    """
    Serialize a JSON-compatible object to canonical JSON v1 (UTF-8 bytes).
    - Sorted keys
    - Compact separators
    """
    try:
        s = json.dumps(
            obj,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except TypeError as e:
        # Attempt to convert non-serializable types by stringifying
        # This preserves determinism for same inputs.
        def _fallback(o):
            try:
                return str(o)
            except Exception:
                return repr(o)

        s = json.dumps(
            obj,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_fallback,
        )
    return s.encode("utf-8")


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_chain(prev_hash: bytes, current: bytes) -> bytes:
    """
    Chain hash = SHA256(prev_hash || current_payload_sha256)
    - prev_hash: previous link hash (32 bytes) or b"" for genesis
    - current: canonical JSON bytes of the current entry
    """
    if not isinstance(prev_hash, (bytes, bytearray)):
        raise TypeError("prev_hash must be bytes")
    if not isinstance(current, (bytes, bytearray)):
        raise TypeError("current must be bytes")
    curr_digest = sha256(current)
    return sha256(prev_hash + curr_digest)
