# -*- coding: utf-8 -*-
"""
Django management command — seal_laby_bundle

Packages the daily Laby (honeypot) JSONL log into a verifiable bundle:
- Collects JSONL entries for a given UTC date (default: today UTC)
- Builds a manifest (count, first/last timestamps, first/last chain_hash)
- Writes final_hash.txt (the last chain_hash of the day)
- Produces a ZIP bundle (events.jsonl, manifest.json, final_hash.txt)
- Generates a detached PGP signature (.sig) of final_hash.txt (optional, if key provided)
- Uploads bundle and signature to Nextcloud via WebDAV (optional)
- Sends a webhook notification (optional)

Environment variables (defaults shown):
- LABY_JSONL_PATH=/tmp/laby_events.jsonl
- LABY_CHAIN_STATE_PATH=/tmp/laby_chain.state
- LABY_WEBHOOK_URL=""                       # for canary events; see also SEAL_WEBHOOK_URL below

- SEAL_PGP_PRIVATE_KEY=""                  # ASCII-armored private key for seal signing (optional)
- SEAL_PGP_PASSPHRASE=""                   # Passphrase for the PGP private key (optional)

- NEXTCLOUD_WEBDAV_BASE_URL=""             # e.g. https://nc.example.com/remote.php/dav/files/USER
- NEXTCLOUD_USERNAME=""
- NEXTCLOUD_PASSWORD=""
- NEXTCLOUD_FOLDER="laby-seals"            # Folder in WebDAV base to upload to (auto-create)
- NEXTCLOUD_PUBLIC_BASE_URL=""             # Public base URL to build share-ish links (optional)

- SEAL_WEBHOOK_URL=""                      # n8n (or similar) webhook to notify seal results

Usage:
    python manage.py seal_laby_bundle
    python manage.py seal_laby_bundle --date 2025-10-06
    python manage.py seal_laby_bundle --jsonl /var/log/laby.jsonl --out-dir /tmp/out
    python manage.py seal_laby_bundle --no-upload --no-sign --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from django.core.management.base import BaseCommand, CommandError


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _utc_today_str() -> str:
    return dt.datetime.utcnow().date().isoformat()


def _parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def _iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    # Skip malformed lines
                    continue
    except FileNotFoundError:
        return
    except Exception:
        return


def _filter_entries_for_date(
    entries: Iterable[Dict[str, Any]], day: dt.date
) -> List[Dict[str, Any]]:
    day_prefix = day.isoformat()
    # ts_utc in entries is expected to be ISO "YYYY-MM-DDTHH:MM:SSZ"
    out: List[Dict[str, Any]] = []
    for e in entries:
        ts = str(e.get("ts_utc") or "")
        if ts.startswith(day_prefix):
            out.append(e)
    return out


def _first_last_hash(entries: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    first = entries[0].get("chain_hash") if entries else None
    last = entries[-1].get("chain_hash") if entries else None
    return (str(first) if first else None, str(last) if last else None)


def _read_chain_state(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
            return s or None
    except Exception:
        return None


def _pgp_sign_detached(plaintext: str, priv_key_asc: str, passphrase: str | None) -> str:
    """
    Returns ASCII-armored detached signature over the plaintext.
    Requires pgpy to be installed (already in Poetry deps: pgpy).
    """
    try:
        import pgpy  # type: ignore
    except Exception as e:
        raise RuntimeError("pgpy not available for PGP signing") from e

    key, _ = pgpy.PGPKey.from_blob(priv_key_asc)
    if key.is_protected and passphrase:
        key.unlock(passphrase)

    msg = pgpy.PGPMessage.new(plaintext)
    # Create detached signature
    sig = key.sign(msg, detached=True)
    return str(sig)


def _ensure_trailing_slash(u: str) -> str:
    return u if u.endswith("/") else (u + "/")


def _mkcol(url: str, auth: Tuple[str, str]) -> None:
    # Try to create collection; ignore errors (exists or not supported)
    try:
        requests.request("MKCOL", url, auth=auth, timeout=8)
    except Exception:
        pass


def _webdav_upload_put(url: str, content: bytes, auth: Tuple[str, str], content_type: str) -> None:
    r = requests.put(
        url, data=content, headers={"Content-Type": content_type}, auth=auth, timeout=30
    )
    if r.status_code >= 400:
        raise CommandError(f"Nextcloud PUT failed {r.status_code}: {r.text[:200]}")


def _to_bytes(s: str) -> bytes:
    return s.encode("utf-8")


@dataclass
class SealResult:
    date: str
    count: int
    final_hash: str | None
    bundle_name: str
    uploaded_urls: Dict[str, str]
    webhook_status: Optional[int]


class Command(BaseCommand):
    help = "Seal Laby daily bundle (JSONL + manifest + final_hash + PGP sig) and upload to Nextcloud; send webhook."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--date",
            dest="date",
            default=_utc_today_str(),
            help="UTC date YYYY-MM-DD (default: today UTC)",
        )
        parser.add_argument(
            "--jsonl", dest="jsonl", default=_env("LABY_JSONL_PATH", "/tmp/laby_events.jsonl")
        )
        parser.add_argument(
            "--chain", dest="chain", default=_env("LABY_CHAIN_STATE_PATH", "/tmp/laby_chain.state")
        )
        parser.add_argument(
            "--out-dir",
            dest="out_dir",
            default=None,
            help="Local directory to copy final ZIP/signature (optional)",
        )
        parser.add_argument(
            "--no-upload", dest="no_upload", action="store_true", help="Do not upload to Nextcloud"
        )
        parser.add_argument(
            "--no-sign", dest="no_sign", action="store_true", help="Do not produce PGP signature"
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Do not upload or send webhook; just build locally",
        )

    def handle(self, *args, **opts) -> None:
        day = _parse_date(str(opts["date"]))
        jsonl_path = str(opts["jsonl"])
        chain_state_path = str(opts["chain"])
        out_dir_opt = opts.get("out_dir") or ""
        no_upload = bool(opts.get("no_upload"))
        no_sign = bool(opts.get("no_sign"))
        dry_run = bool(opts.get("dry_run"))

        self.stdout.write(self.style.NOTICE(f"Sealing Laby bundle for {day.isoformat()}"))
        entries = list(_iter_jsonl(jsonl_path))
        day_entries = _filter_entries_for_date(entries, day)
        count = len(day_entries)
        first_hash, last_hash = _first_last_hash(day_entries)

        # Fallback final hash from chain state if empty day
        final_hash = last_hash or _read_chain_state(chain_state_path)

        self.stdout.write(f"- Entries total: {len(entries)}, day({day}): {count}")
        self.stdout.write(f"- First hash (day): {first_hash or '—'}")
        self.stdout.write(f"- Final hash (day or chain): {final_hash or '—'}")

        if count == 0 and not final_hash:
            raise CommandError("No entries for the day and chain state missing; cannot seal.")

        # Build bundle in temp dir
        with tempfile.TemporaryDirectory(prefix="laby_seal_") as tmpd:
            tmpd = os.path.abspath(tmpd)
            date_str = day.isoformat()
            events_name = f"events-{date_str}.jsonl"
            manifest_name = "manifest.json"
            final_hash_name = "final_hash.txt"
            sig_name = "final_hash.sig"
            bundle_name = f"laby_bundle_{date_str}.zip"

            events_path = os.path.join(tmpd, events_name)
            manifest_path = os.path.join(tmpd, manifest_name)
            final_hash_path = os.path.join(tmpd, final_hash_name)
            sig_path = os.path.join(tmpd, sig_name)
            bundle_path = os.path.join(tmpd, bundle_name)

            # Write events jsonl (day subset)
            with open(events_path, "w", encoding="utf-8") as f:
                for e in day_entries:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")

            # Manifest
            manifest: Dict[str, Any] = {
                "date": date_str,
                "count": count,
                "first_ts": day_entries[0]["ts_utc"] if count else None,
                "last_ts": day_entries[-1]["ts_utc"] if count else None,
                "first_hash": first_hash,
                "final_hash": final_hash,
                "source": {
                    "jsonl_path": jsonl_path,
                    "chain_state_path": chain_state_path,
                },
                "notes": "Honeypot seal bundle — JSONL entries for the day + final chain hash.",
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            # Final hash file
            with open(final_hash_path, "w", encoding="utf-8") as f:
                f.write((final_hash or "") + "\n")

            # Optional PGP detached signature of final_hash.txt
            signature_bytes: Optional[bytes] = None
            if not no_sign:
                pgp_priv = _env("SEAL_PGP_PRIVATE_KEY", "")
                pgp_pass = _env("SEAL_PGP_PASSPHRASE", "")
                if pgp_priv.strip():
                    with open(final_hash_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    try:
                        sig_asc = _pgp_sign_detached(content, pgp_priv, pgp_pass or None)
                        signature_bytes = _to_bytes(sig_asc)
                        with open(sig_path, "wb") as f:
                            f.write(signature_bytes)
                        self.stdout.write(self.style.SUCCESS("- PGP detached signature generated."))
                    except Exception as e:
                        raise CommandError(f"PGP signing failed: {e}") from e
                else:
                    self.stdout.write(self.style.WARNING("- PGP signing skipped (no key in env)."))
            else:
                self.stdout.write(self.style.WARNING("- PGP signing disabled by flag."))

            # ZIP bundle
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.write(events_path, arcname=events_name)
                z.write(manifest_path, arcname=manifest_name)
                z.write(final_hash_path, arcname=final_hash_name)
                if not no_sign and os.path.exists(sig_path):
                    z.write(sig_path, arcname=sig_name)

            self.stdout.write(self.style.SUCCESS(f"- Bundle created: {bundle_path}"))

            # Optionally copy to out_dir
            if out_dir_opt:
                os.makedirs(out_dir_opt, exist_ok=True)
                dst_bundle = os.path.join(out_dir_opt, bundle_name)
                with open(bundle_path, "rb") as src, open(dst_bundle, "wb") as dst:
                    dst.write(src.read())
                if not no_sign and os.path.exists(sig_path):
                    dst_sig = os.path.join(out_dir_opt, sig_name)
                    with open(sig_path, "rb") as src, open(dst_sig, "wb") as dst:
                        dst.write(src.read())
                self.stdout.write(self.style.SUCCESS(f"- Copied bundle to {dst_bundle}"))

            uploaded_urls: Dict[str, str] = {}
            webhook_status: Optional[int] = None

            # Upload to Nextcloud via WebDAV
            if not (no_upload or dry_run):
                nc_base = _env("NEXTCLOUD_WEBDAV_BASE_URL", "").strip()
                nc_user = _env("NEXTCLOUD_USERNAME", "").strip()
                nc_pass = _env("NEXTCLOUD_PASSWORD", "").strip()
                nc_folder = _env("NEXTCLOUD_FOLDER", "laby-seals").strip()
                nc_public_base = _env("NEXTCLOUD_PUBLIC_BASE_URL", "").strip()
                if nc_base and nc_user and nc_pass:
                    auth = (nc_user, nc_pass)
                    base = _ensure_trailing_slash(nc_base)
                    folder = nc_folder.strip("/")

                    date_dir_url = base + folder + "/" + day.isoformat() + "/"
                    # Ensure folders
                    _mkcol(base + folder, auth)
                    _mkcol(date_dir_url, auth)

                    # PUT bundle
                    with open(bundle_path, "rb") as f:
                        content = f.read()
                    bundle_url = date_dir_url + bundle_name
                    _webdav_upload_put(bundle_url, content, auth, "application/zip")
                    uploaded_urls["bundle"] = bundle_url

                    # PUT signature (if exists)
                    if not no_sign and os.path.exists(sig_path):
                        with open(sig_path, "rb") as f:
                            content = f.read()
                        sig_url = date_dir_url + sig_name
                        _webdav_upload_put(sig_url, content, auth, "application/pgp-signature")
                        uploaded_urls["signature"] = sig_url

                    # Public-ish links if provided
                    if nc_public_base:
                        pub_base = (
                            _ensure_trailing_slash(nc_public_base)
                            + folder
                            + "/"
                            + day.isoformat()
                            + "/"
                        )
                        uploaded_urls["bundle_public"] = pub_base + bundle_name
                        if "signature" in uploaded_urls:
                            uploaded_urls["signature_public"] = pub_base + sig_name

                    self.stdout.write(self.style.SUCCESS("- Upload to Nextcloud complete."))
                else:
                    self.stdout.write(
                        self.style.WARNING("- Nextcloud upload skipped (missing env config).")
                    )
            elif dry_run:
                self.stdout.write(self.style.WARNING("- Dry-run: skipping upload."))
            else:
                self.stdout.write(self.style.WARNING("- Upload disabled by flag."))

            # Webhook notify
            if not dry_run:
                webhook_url = _env("SEAL_WEBHOOK_URL", "").strip()
                if webhook_url:
                    payload = {
                        "type": "laby_seal",
                        "date": day.isoformat(),
                        "count": count,
                        "final_hash": final_hash,
                        "urls": uploaded_urls,
                        "ts_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    }
                    try:
                        r = requests.post(webhook_url, json=payload, timeout=10)
                        webhook_status = r.status_code
                        if r.ok:
                            self.stdout.write(self.style.SUCCESS("- Webhook notified."))
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"- Webhook returned {r.status_code}: {r.text[:200]}"
                                )
                            )
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"- Webhook notify failed: {e}"))
                else:
                    self.stdout.write(
                        self.style.WARNING("- Webhook skipped (SEAL_WEBHOOK_URL not set).")
                    )
            else:
                self.stdout.write(self.style.WARNING("- Dry-run: skipping webhook."))

            # Report summary
            result = SealResult(
                date=day.isoformat(),
                count=count,
                final_hash=final_hash,
                bundle_name=bundle_name,
                uploaded_urls=uploaded_urls,
                webhook_status=webhook_status,
            )
            self.stdout.write(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
            self.stdout.write(self.style.SUCCESS("Seal Laby bundle completed."))
