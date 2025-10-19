#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_allowlist_expiry.py
-------------------------

Externalized checker for a CVE allowlist with expiration.

- Reads security/allowlist.yml (default) and validates:
  - entries[].cve (or entries[].id) is present and non-empty
  - entries[].justification present and non-empty
  - entries[].expires_at parseable as ISO date/datetime (YYYY-MM-DD or ISO8601)
  - expires_at:
      * not expired (now <= expires_at)
      * not beyond max-days (default: 14 days)
- Optionally validates that each allowlisted CVE actually exists in a provided
  vulnerabilities JSON report (e.g., pip-audit/osv-scanner/npm audit normalized JSON):
  - Every entry.cve must be present in the set of discovered vulnerabilities
    (via --vuln-json); otherwise: fail (drift / stale allowlist).

Exit codes:
  0 = OK (or skipped if allowlist file not found)
  1 = Validation errors

Usage:
  python scripts/check_allowlist_expiry.py \
      --path security/allowlist.yml \
      --max-days 14 \
      --vuln-json path/to/vuln_report.json

The --vuln-json format is flexible; the script attempts to collect vulnerability IDs
(CVE, GHSA, OSV IDs) from common JSON schemas (pip-audit, osv-scanner, npm audit, or
a custom array of objects with id/cve/aliases).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

try:
    import yaml  # type: ignore
except Exception as e:  # pragma: no cover
    print(
        json.dumps(
            {
                "ok": False,
                "error": "PyYAML is required to parse allowlist YAML.",
                "detail": str(e),
            }
        )
    )
    sys.exit(1)


def now_utc() -> dt.datetime:
    # Naive UTC to keep consistency with simple ISO parsing (no tzinfo)
    return dt.datetime.utcnow().replace(microsecond=0)


def parse_iso_datetime(value: str) -> Optional[dt.datetime]:
    """
    Parse an ISO-like string:
    - YYYY-MM-DD
    - YYYY-MM-DDTHH:MM:SS
    - YYYY-MM-DDTHH:MM:SSZ
    Returns naive UTC datetime (no tzinfo) or None.
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    # Normalize trailing 'Z' (UTC)
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1]
    # Allow date-only
    try:
        if "T" in s:
            return dt.datetime.fromisoformat(s)
        # date-only
        return dt.datetime.fromisoformat(s + "T00:00:00")
    except Exception:
        return None


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def to_upper_id(s: str) -> str:
    return (s or "").strip().upper()


def collect_ids_from_obj(obj: Dict[str, Any], out: Set[str]) -> None:
    """
    Attempt to collect vulnerability IDs from a generic object.
    Common key names: id, cve, ghsa_id, vulnerability_id, aliases.
    """
    # Single-value keys
    for key in ("id", "cve", "ghsa_id", "vulnerability_id", "CVE", "GHSA"):
        if key in obj and isinstance(obj[key], str) and obj[key].strip():
            out.add(to_upper_id(obj[key]))

    # Aliases array
    aliases = obj.get("aliases")
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and a.strip():
                out.add(to_upper_id(a))

    # Sometimes nested objects contain IDs
    advisory = obj.get("advisory")
    if isinstance(advisory, dict):
        # Try advisory.id or advisory.cve or advisory.ghsa_id
        for key in ("id", "cve", "ghsa_id"):
            val = advisory.get(key)
            if isinstance(val, str) and val.strip():
                out.add(to_upper_id(val))
        aliases2 = advisory.get("aliases")
        if isinstance(aliases2, list):
            for a in aliases2:
                if isinstance(a, str) and a.strip():
                    out.add(to_upper_id(a))


def collect_ids_from_json(data: Any) -> Set[str]:
    """
    Build a set of vulnerability IDs from a variety of JSON shapes.
    Supports:
      - array of objects with id/cve/aliases...
      - object with "vulnerabilities": [...]
      - object with "results" or "issues" (common in scanners)
    """
    ids: Set[str] = set()

    def scan_any(node: Any) -> None:
        if isinstance(node, dict):
            # direct object
            collect_ids_from_obj(node, ids)
            # look into common arrays
            for key in ("vulnerabilities", "results", "issues", "data", "items"):
                child = node.get(key)
                if isinstance(child, list):
                    for it in child:
                        scan_any(it)
            # also scan other dict items
            for v in node.values():
                if isinstance(v, (dict, list)):
                    scan_any(v)
        elif isinstance(node, list):
            for it in node:
                scan_any(it)

    scan_any(data)
    return ids


def validate_allowlist(
    allowlist: Dict[str, Any],
    max_days: int,
    present_ids: Optional[Set[str]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate allowlist structure and expiration rules.
    - present_ids: if provided, each allowlisted CVE must be present (else drift).
    """
    errors: List[str] = []
    warnings: List[str] = []

    entries = allowlist.get("entries")
    if entries is None:
        return True, {
            "ok": True,
            "errors": [],
            "warnings": ["No 'entries' found; allowlist considered empty."],
            "checked": 0,
        }

    if not isinstance(entries, list):
        errors.append("'entries' must be a list.")
        return False, {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "checked": 0,
        }

    now = now_utc()
    checked = 0

    for idx, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"entries[{idx}]: not an object")
            continue

        raw_id = (e.get("cve") or e.get("id") or "").strip()
        if not raw_id:
            errors.append(f"entries[{idx}]: missing 'cve' (or 'id')")
            continue

        cve = to_upper_id(raw_id)
        justif = (e.get("justification") or "").strip()
        if not justif:
            errors.append(f"{cve}: missing 'justification'")
        elif len(justif) < 4:
            warnings.append(f"{cve}: justification too short")

        raw_exp = (e.get("expires_at") or "").strip()
        exp = parse_iso_datetime(raw_exp)
        if not exp:
            errors.append(f"{cve}: invalid 'expires_at' format (expected YYYY-MM-DD or ISO8601)")
            continue

        # Expired?
        if now > exp:
            errors.append(f"{cve}: expired at {raw_exp}")

        # Beyond max-days?
        delta = (exp - now).total_seconds()
        if delta > max_days * 24 * 3600:
            errors.append(
                f"{cve}: expiration beyond {max_days} days is not allowed (expires_at={raw_exp})"
            )

        # If a vulnerabilities report is provided, ensure the allowlist entry is present.
        if present_ids is not None:
            if cve not in present_ids:
                # We also check if the ID appears as GHSA alias or vice-versa
                present_upper = {s.upper() for s in present_ids}
                if cve not in present_upper:
                    errors.append(f"{cve}: not present in current vulnerabilities report")

        checked += 1

    return (len(errors) == 0), {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checked": checked,
        "now_utc": now.isoformat() + "Z",
        "max_days": max_days,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Validate allowlist CVE YAML with expiration and drift checks."
    )
    ap.add_argument(
        "--path",
        default="security/allowlist.yml",
        help="Path to allowlist YAML (default: security/allowlist.yml)",
    )
    ap.add_argument(
        "--max-days",
        type=int,
        default=14,
        help="Maximum allowed expiration window in days (default: 14)",
    )
    ap.add_argument(
        "--vuln-json",
        default=None,
        help="Optional path to a vulnerabilities JSON report to verify allowlist entries are present.",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (e.g., too-short justifications).",
    )
    args = ap.parse_args()

    path = args.path
    max_days = args.max_days
    vuln_json_path = args.vuln_json
    strict = args.strict

    if not os.path.exists(path):
        # No allowlist — return OK but note skipped.
        print(json.dumps({"ok": True, "skipped": True, "reason": f"file not found: {path}"}))
        sys.exit(0)

    try:
        allow = load_yaml(path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to parse YAML: {e}"}))
        sys.exit(1)

    present_ids: Optional[Set[str]] = None
    if vuln_json_path:
        if not os.path.exists(vuln_json_path):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"Vulnerabilities JSON not found: {vuln_json_path}",
                    }
                )
            )
            sys.exit(1)
        try:
            with open(vuln_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            present_ids = collect_ids_from_json(data)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"Failed to parse vulnerabilities JSON: {e}"}))
            sys.exit(1)

    ok, res = validate_allowlist(allow, max_days=max_days, present_ids=present_ids)

    # Promote warnings to errors if strict
    if strict and res.get("warnings"):
        res["errors"] = (res.get("errors") or []) + res["warnings"]  # type: ignore
        res["warnings"] = []
        ok = False

    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
