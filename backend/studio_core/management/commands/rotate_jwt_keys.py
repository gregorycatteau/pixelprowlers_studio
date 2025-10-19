# -*- coding: utf-8 -*-
"""
Django management command — rotate_jwt_keys

But / Why
- Rotate RS256 keys (SIGNING/VERIFYING) safely and publish a JWK Set (JWKS).
- Produce a new RSA keypair with a kid header, and optionally compose a JWKS
  including the previous public key for a 24h overlap window (“validating only”).
- Output files/snippets to wire env vars (per realm) and a jwks.json artifact.

This command does NOT hot‑reload Django settings for running processes.
You must deploy the new env (SIGNING/VERIFYING keys + JWT_KID) and restart.

Typical rotation workflow (per realm)
1) Generate a new pair + JWKS that includes both: {new(active), old(validating)}.
2) Deploy:
   - Set env:
       <REALM>_JWT_PRIVATE_KEY=<new_private_pem>
       <REALM>_JWT_PUBLIC_KEY=<new_public_pem>
       JWT_KID=<new_kid>
   - Expose JWKS with both keys (new first).
   - Restart app(s).
3) After overlap window (e.g., 24h), publish JWKS with only the new key.

Examples
  python manage.py rotate_jwt_keys --realm dojo --out-dir ./secrets \
    --jwks-out ./secrets/jwks.json

  python manage.py rotate_jwt_keys --realm clients --kid clients-kid-20251006 \
    --prev-public ./secrets/old_public.pem --prev-kid clients-kid-20250905 \
    --jwks-out ./secrets/jwks_overlap.json --print-env

Notes
- Realms supported: dojo, clients, laby (defines which env var prefix to print).
- JWKS is written to a file if --jwks-out is passed; otherwise it’s printed.
- Requires the 'cryptography' library to generate keys and derive JWK.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from django.core.management.base import BaseCommand, CommandError

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except Exception as e:  # pragma: no cover
    # We raise in handle() with a clearer message
    serialization = None
    rsa = None
    default_backend = None


@dataclass
class KeyPair:
    private_pem: str
    public_pem: str
    kid: str
    alg: str = "RS256"
    kty: str = "RSA"


REALM_PREFIX = {
    "dojo": "DOJO",
    "clients": "CLIENTS",
    "laby": "LABY",
}


def _b64u_uint(val: int) -> str:
    b = val.to_bytes((val.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _public_pem_to_jwk(public_pem: str, kid: str, alg: str = "RS256") -> dict:
    """
    Convert an RSA public PEM to JWK dict {kty, use, alg, kid, n, e}.
    """
    if serialization is None:
        raise RuntimeError("The 'cryptography' package is required to derive JWK from PEM.")
    pub = serialization.load_pem_public_key(public_pem.encode("utf-8"), backend=default_backend())
    numbers = pub.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": alg,
        "kid": kid,
        "n": _b64u_uint(numbers.n),
        "e": _b64u_uint(numbers.e),
    }


def _generate_rsa_keypair(bits: int = 2048) -> Tuple[str, str]:
    """
    Generate an RSA private/public key pair (PEM-encoded).
    """
    if rsa is None or serialization is None:
        raise RuntimeError("The 'cryptography' package is required to generate RSA keys.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits, backend=default_backend())
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


class Command(BaseCommand):
    help = "Rotate RS256 JWT keys and compose a JWK Set (JWKS) for publication."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--realm",
            choices=("dojo", "clients", "laby"),
            default="clients",
            help="Which realm to output env var hints for (default: clients).",
        )
        parser.add_argument(
            "--kid",
            default=None,
            help="KID for the new key (default: <realm>-kid-<UTC timestamp>).",
        )
        parser.add_argument(
            "--bits",
            type=int,
            default=2048,
            help="RSA key size in bits (default: 2048).",
        )
        parser.add_argument(
            "--out-dir",
            default=None,
            help="Directory to write new_private.pem and new_public.pem (optional).",
        )
        parser.add_argument(
            "--jwks-out",
            default=None,
            help="Path to write jwks.json (if omitted, prints JWKS to stdout).",
        )
        parser.add_argument(
            "--prev-public",
            default=None,
            help="Path to previous public key PEM to include as 'validating only' (overlap).",
        )
        parser.add_argument(
            "--prev-kid",
            default=None,
            help="KID of the previous key (required if --prev-public is used).",
        )
        parser.add_argument(
            "--print-env",
            action="store_true",
            help="Print export instructions for env vars (per realm prefix).",
        )

    def handle(self, *args, **opts) -> None:
        if rsa is None or serialization is None:
            raise CommandError(
                "cryptography is required. Install it in your environment to generate/parse RSA keys."
            )

        realm: str = opts["realm"]
        bits: int = int(opts["bits"])
        kid: str = opts["kid"] or f"{realm}-kid-{_now_ts()}"
        out_dir: Optional[str] = opts.get("out_dir") or None
        jwks_out: Optional[str] = opts.get("jwks_out") or None
        prev_public_path: Optional[str] = opts.get("prev_public") or None
        prev_kid: Optional[str] = opts.get("prev_kid") or None
        print_env: bool = bool(opts.get("print_env"))

        # Generate new keypair
        new_priv_pem, new_pub_pem = _generate_rsa_keypair(bits=bits)
        kp = KeyPair(private_pem=new_priv_pem, public_pem=new_pub_pem, kid=kid)

        # Compose JWKS keys: new first
        try:
            new_jwk = _public_pem_to_jwk(kp.public_pem, kid=kp.kid, alg=kp.alg)
        except Exception as e:
            raise CommandError(f"Failed to derive JWK from new public key: {e}") from e

        keys = [new_jwk]

        if prev_public_path:
            if not prev_kid:
                raise CommandError("--prev-kid is required when --prev-public is provided.")
            try:
                prev_pub_pem = Path(prev_public_path).read_text(encoding="utf-8")
            except Exception as e:
                raise CommandError(f"Failed to read previous public key: {e}") from e
            try:
                prev_jwk = _public_pem_to_jwk(prev_pub_pem, kid=prev_kid, alg=kp.alg)
            except Exception as e:
                raise CommandError(f"Failed to derive JWK from previous public key: {e}") from e
            keys.append(prev_jwk)

        jwks = {"keys": keys}

        # Write outputs if requested
        if out_dir:
            target = Path(out_dir)
            target.mkdir(parents=True, exist_ok=True)
            (target / "new_private.pem").write_text(kp.private_pem, encoding="utf-8")
            (target / "new_public.pem").write_text(kp.public_pem, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Written: {target / 'new_private.pem'}"))
            self.stdout.write(self.style.SUCCESS(f"Written: {target / 'new_public.pem'}"))

        if jwks_out:
            out_path = Path(jwks_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(jwks, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Written JWKS: {out_path}"))
        else:
            # Print JWKS to stdout (useful for quick copy)
            self.stdout.write(json.dumps(jwks, ensure_ascii=False, indent=2))

        # Print env instructions for the selected realm
        if print_env:
            prefix = REALM_PREFIX.get(realm, realm.upper())
            # For realms, codebase expects <PREFIX>_JWT_PRIVATE_KEY / <PREFIX>_JWT_PUBLIC_KEY + JWT_KID
            self.stdout.write("")
            self.stdout.write(
                self.style.NOTICE("Export instructions (shell) — adapt to your secret store:")
            )
            self.stdout.write("# --- BEGIN copy-paste ---")
            # Warn about multiline values
            self.stdout.write(
                "# Note: The values below are multiline PEMs; prefer secret managers or heredoc files."
            )
            self.stdout.write(f"# Realm: {realm}  |  KID: {kp.kid}  |  ALG: {kp.alg}")
            # Write PEMs to files then export as file refs (recommended pattern)
            self.stdout.write("cat > new_private.pem <<'EOF_PRIV'")
            self.stdout.write(kp.private_pem.strip())
            self.stdout.write("EOF_PRIV")
            self.stdout.write("cat > new_public.pem <<'EOF_PUB'")
            self.stdout.write(kp.public_pem.strip())
            self.stdout.write("EOF_PUB")
            self.stdout.write("")
            self.stdout.write(f'export {prefix}_JWT_PRIVATE_KEY="$(cat new_private.pem)"')
            self.stdout.write(f'export {prefix}_JWT_PUBLIC_KEY="$(cat new_public.pem)"')
            self.stdout.write(f"export JWT_KID='{kp.kid}'")
            self.stdout.write("# --- END copy-paste ---")

        # Print next steps
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("Next steps:"))
        self.stdout.write(
            "- Deploy the new SIGNING/VERIFYING keys and JWT_KID as environment/secret variables."
        )
        self.stdout.write(
            "- Ensure the JWKS endpoint publishes the new key first; include the previous key during overlap."
        )
        self.stdout.write("- Restart application processes to pick up new settings.")
        self.stdout.write(
            "- After the overlap window (e.g., 24h), publish JWKS with only the new key."
        )
        self.stdout.write(self.style.SUCCESS("Rotation material generated successfully."))
