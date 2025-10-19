# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_core.obs.canonical_json import sha256_chain, sha256_hex, to_canonical
from studio_core.obs.journal import append_event_to, verify_chain


def test_canonical_json_deterministic_hash():
    a = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    b = {"nested": {"x": 1, "y": 2}, "a": 1, "b": 2}
    ca = to_canonical(a)
    cb = to_canonical(b)
    # Même bytes (tri de clés, compact)
    assert ca == cb
    # Même hash sur toute plateforme
    assert sha256_hex(ca) == sha256_hex(cb)

    # Données différentes -> hash différent
    c = {"nested": {"x": 1, "y": 3}, "a": 1, "b": 2}
    cc = to_canonical(c)
    assert sha256_hex(ca) != sha256_hex(cc)


def test_hash_chain_integrity(tmp_path: Path, monkeypatch):
    # Utiliser un fichier de journal temporaire
    log_path = tmp_path / "auth_journal.log"

    # Append deux événements PII-safe
    h1 = append_event_to(
        str(log_path), {"source": "auth", "endpoint": "login", "decision": "pending"}
    )
    assert isinstance(h1, str) and len(h1) == 64
    h2 = append_event_to(str(log_path), {"source": "auth", "endpoint": "eotp", "decision": "ok"})
    assert isinstance(h2, str) and len(h2) == 64

    # Intégrité OK
    ok, checked, err = verify_chain(str(log_path), deep=True)
    assert ok is True
    assert checked >= 2
    assert err is None

    # Corrompre la 1ère ligne et vérifier la détection
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines and len(lines) >= 2
    first = json.loads(lines[0])
    if first.get("type") == "event":
        # Altération du payload (décision)
        first["payload"]["decision"] = "tampered"
        lines[0] = json.dumps(first, separators=(",", ":"), ensure_ascii=False)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        ok2, checked2, err2 = verify_chain(str(log_path), deep=True)
        assert ok2 is False
        # L'erreur peut être 'hash_mismatch' ou 'prev_link_mismatch' suivant la position
        assert err2 in {
            "hash_mismatch",
            "prev_link_mismatch",
            "malformed_json",
            "unknown_record_type",
        }
