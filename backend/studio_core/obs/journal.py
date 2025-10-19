# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Append-only auth journal with Canonical JSON v1 + Hash-Chaining (adapter-first).

Design:
- Each record is a canonical JSON line (UTF-8), type:
  - {"type":"event","ts":...,"payload":{...}, "prev":"<hex>", "hash":"<hex>"}
  - {"type":"anchor","ts":...,"anchor_hash":"<hex>","count":N}
- Chain rule: H_i = SHA256(H_{i-1} || SHA256(canonical(payload_i)))
  where H_0 = b"" (genesis)
- Append-only: records are only appended; any alteration is detected by verification.
- State sidecar: a small JSON state file maintains last hash & count for O(1) append.

Configuration:
- OBS_JOURNAL_FILE: target file path (default: <BASE_DIR>/var/auth_journal.log)
- OBS_JOURNAL_STATE: state file path (default: <BASE_DIR>/var/auth_journal.state.json)
- OBS_ANCHOR_EVERY: write an anchor record every N events (default: 100)
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from django.conf import settings

from .canonical_json import sha256, sha256_chain, sha256_hex, to_canonical


def _base_dir() -> Path:
    try:
        return Path(getattr(settings, "BASE_DIR"))
    except Exception:
        return Path(os.getcwd())


def _default_files() -> Tuple[Path, Path]:
    base = _base_dir()
    log_path = Path(os.getenv("OBS_JOURNAL_FILE", str(base / "var" / "auth_journal.log")))
    state_path = Path(os.getenv("OBS_JOURNAL_STATE", str(base / "var" / "auth_journal.state.json")))
    return log_path, state_path


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class _State:
    last_hash_hex: str
    count: int

    @classmethod
    def load(cls, path: Path) -> "_State":
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(
                    last_hash_hex=str(data.get("last_hash_hex") or ""),
                    count=int(data.get("count") or 0),
                )
        except Exception:
            pass
        return cls(last_hash_hex="", count=0)

    def save(self, path: Path) -> None:
        try:
            _ensure_parent(path)
            path.write_text(
                json.dumps({"last_hash_hex": self.last_hash_hex, "count": self.count}),
                encoding="utf-8",
            )
        except Exception:
            # Non-bloquant: en cas d'échec, la vérification complète peut reconstruire l'état
            pass


def append_event(payload: Dict[str, Any], file_path: Optional[str] = None) -> str:
    """
    Append an event to the journal. Returns the new record hash (hex).
    - payload must be JSON-serializable and PII-safe.
    """
    log_path, state_path = _default_files()
    if file_path:
        log_path = Path(file_path)
        state_path = log_path.with_suffix(".state.json")

    state = _State.load(state_path)
    prev_hash = bytes.fromhex(state.last_hash_hex) if state.last_hash_hex else b""

    canonical = to_canonical(payload)  # bytes
    new_hash = sha256_chain(prev_hash, canonical)
    rec = {
        "type": "event",
        "ts": int(time.time()),
        "payload": payload,
        "prev": state.last_hash_hex,  # hex of previous
        "hash": new_hash.hex(),
    }

    # Append line
    _ensure_parent(log_path)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False))
        f.write("\n")

    # Update state
    state.last_hash_hex = new_hash.hex()
    state.count += 1

    # Anchor every N events
    try:
        anchor_every = int(os.getenv("OBS_ANCHOR_EVERY", "100"))
    except Exception:
        anchor_every = 100
    if anchor_every > 0 and state.count % anchor_every == 0:
        anchor = {
            "type": "anchor",
            "ts": int(time.time()),
            "anchor_hash": state.last_hash_hex,
            "count": state.count,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(anchor, separators=(",", ":"), ensure_ascii=False))
            f.write("\n")

    state.save(state_path)
    return state.last_hash_hex


def verify_chain(
    file_path: Optional[str] = None, deep: bool = True
) -> Tuple[bool, int, Optional[str]]:
    """
    Verify the hash chain integrity.
    Returns (ok, checked_records, error_message)
    - If deep=False, stops at first error.
    """
    log_path, _ = _default_files()
    if file_path:
        log_path = Path(file_path)
    if not log_path.exists():
        return True, 0, None

    prev = b""
    checked = 0
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    return False, checked, "malformed_json"

                if obj.get("type") == "event":
                    payload = obj.get("payload")
                    want_hash_hex = str(obj.get("hash") or "")
                    prev_hex_in_file = str(obj.get("prev") or "")
                    # Recompute chain
                    canonical = to_canonical(payload)
                    computed = sha256_chain(prev, canonical).hex()
                    if computed != want_hash_hex:
                        return False, checked, "hash_mismatch"
                    # prev stored in file should match our previous link
                    if prev.hex() != prev_hex_in_file:
                        return False, checked, "prev_link_mismatch"
                    prev = bytes.fromhex(want_hash_hex)
                    checked += 1
                elif obj.get("type") == "anchor":
                    # Anchor must reflect current prev hex
                    if str(obj.get("anchor_hash") or "") != prev.hex():
                        return False, checked, "anchor_mismatch"
                else:
                    # Unknown record types are invalid
                    return False, checked, "unknown_record_type"
        return True, checked, None
    except Exception as e:
        return False, checked, str(e)


# Convenience for tests/tools
def append_event_to(path: str, payload: Dict[str, Any]) -> str:
    return append_event(payload, file_path=path)


def _repo_root() -> Path:
    """
    Retourne la racine du dépôt (parent de BASE_DIR qui pointe sur backend/).
    """
    try:
        base = Path(getattr(settings, "BASE_DIR"))
        return base.parent
    except Exception:
        return Path(os.getcwd())


def seal_day(
    signing_key: Optional[str] = None, date: Optional[str] = None, file_path: Optional[str] = None
) -> Path:
    """
    Scelle le journal du jour via hash-chain + HMAC (HMAC-SHA256) et écrit une preuve dans:
      ops/reports/seals/YYYY-MM-DD.txt

    - signing_key: clé HMAC (par défaut OPS_SIGNING_KEY depuis l'env)
    - date: jour à sceller au format YYYY-MM-DD (défaut: aujourd'hui en UTC)
    - file_path: chemin du journal cible (défaut: OBS_JOURNAL_FILE ou <BASE_DIR>/var/auth_journal.log)

    Retourne le chemin du fichier de preuve généré.
    """
    # Résoudre fichiers journal + état
    log_path, state_path = _default_files()
    if file_path:
        log_path = Path(file_path)
        state_path = log_path.with_suffix(".state.json")

    # Lire l'état courant (dernier hash + count)
    state = _State.load(state_path)

    # Vérifier la chaîne avant de sceller
    ok, checked, err = verify_chain(str(log_path), deep=True)
    if not ok:
        raise RuntimeError(f"verify_chain failed: {err} after {checked} records")

    last_hash_hex = state.last_hash_hex or ""
    count = state.count

    # Date à sceller
    from datetime import datetime, timezone

    day_str = (date or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")).strip()
    # Matériau à signer (PII-safe)
    seal_payload = f"date:{day_str}\nlast_hash:{last_hash_hex}\ncount:{count}\n"

    # Clé HMAC
    key = signing_key if signing_key is not None else os.getenv("OPS_SIGNING_KEY", "")
    try:
        import hashlib
        import hmac as _hmac

        sig = (
            _hmac.new(key.encode("utf-8"), seal_payload.encode("utf-8"), hashlib.sha256).hexdigest()
            if key
            else ""
        )
    except Exception:
        sig = ""

    # Écrire la preuve (texte simple)
    repo_root = _repo_root()
    out_dir = repo_root / "ops" / "reports" / "seals"
    out_dir.mkdir(parents=True, exist_ok=True)
    proof_path = out_dir / f"{day_str}.txt"
    with proof_path.open("w", encoding="utf-8") as f:
        f.write(seal_payload)
        f.write(f"hmac_sha256:{sig}\n")
        f.write(f"ts:{int(time.time())}\n")
        if not key:
            f.write("note:OPS_SIGNING_KEY missing; signature non appliquée\n")

    return proof_path
