#!/usr/bin/env python3
"""
check_csp_and_jwks.py — CI helper for CSP, JWKS, and __Host- cookies compliance.

What it checks (depending on flags/inputs):
- JWKS validity at /.well-known/jwks.json (kty=RSA, alg=RS256, kid present, n/e base64url)
- CSP "enforce" headers on key SSR pages (no Report-Only unless instructed)
- (Optional) CSP reports counter at a provided endpoint (expects JSON {"count": 0})
- (Optional) __Host- cookie attributes on an auth response:
  - Names: __Host-pp_refresh and __Host-pp_realm
  - Attributes: HttpOnly; Secure; SameSite=Strict; Path=/; no Domain attribute

Exit code:
  0 — success
  non-zero — failed checks. See printed JSON summary for details.

Usage examples:
  python scripts/check_csp_and_jwks.py \
    --base-url https://clients.local \
    --csp-pages /,/dashboard \
    --cookie-check-url https://clients.local/api/auth/login/ \
    --cookie-method POST \
    --cookie-body-path ci/login_body.json

  python scripts/check_csp_and_jwks.py \
    --base-url https://dojo.local \
    --rotation \
    --csp-pages /,/console \
    --csp-report-check-url https://clients.local/api/csp-report-check
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests


def _json_print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _b64u_decode(s: str) -> bytes:
    # Add padding and decode base64url
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _is_valid_b64u(s: str) -> bool:
    try:
        _b64u_decode(s)
        return True
    except Exception:
        return False


def _fetch(
    url: str,
    method: str = "GET",
    timeout: int = 10,
    insecure: bool = False,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    stream: bool = False,
) -> requests.Response:
    method = method.upper()
    kwargs = {
        "timeout": timeout,
        "verify": not insecure,
        "headers": headers or {},
        "stream": stream,
    }
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = json_body or {}
    resp = requests.request(method, url, **kwargs)
    return resp


def check_jwks(
    base_url: str, jwks_url: Optional[str], rotation: bool, timeout: int, insecure: bool
) -> Tuple[bool, Dict[str, Any]]:
    url = jwks_url or urljoin(base_url, "/.well-known/jwks.json")
    result: Dict[str, Any] = {"url": url, "ok": False, "error": None, "keys": []}
    try:
        resp = _fetch(url, timeout=timeout, insecure=insecure)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return False, result
        data = resp.json()
        if not isinstance(data, dict) or "keys" not in data or not isinstance(data["keys"], list):
            result["error"] = "Invalid JWKS structure"
            return False, result

        keys = data["keys"]
        if len(keys) < 1:
            result["error"] = "No keys in JWKS"
            return False, result

        kids: List[str] = []
        for k in keys:
            # Basic validation
            if not isinstance(k, dict):
                result["error"] = "Key not an object"
                return False, result
            kid = k.get("kid")
            kty = k.get("kty")
            alg = k.get("alg")
            n = k.get("n")
            e = k.get("e")
            if not kid or not isinstance(kid, str):
                result["error"] = "kid missing or not a string"
                return False, result
            if kty != "RSA":
                result["error"] = f"kty not RSA (got {kty})"
                return False, result
            if alg != "RS256":
                result["error"] = f"alg not RS256 (got {alg})"
                return False, result
            if not (
                isinstance(n, str)
                and isinstance(e, str)
                and _is_valid_b64u(n)
                and _is_valid_b64u(e)
            ):
                result["error"] = "n/e invalid or not base64url"
                return False, result
            kids.append(kid)

        # Rotation mode: allow 2 keys (or more), require distinct kids
        if rotation and len(set(kids)) < 2:
            result["error"] = "Rotation mode: expected at least 2 distinct kid values"
            return False, result

        result["keys"] = kids
        result["ok"] = True
        return True, result
    except Exception as e:
        result["error"] = f"Exception: {e}"
        return False, result


def check_csp_pages(
    base_url: str,
    pages: List[str],
    require_enforce: bool,
    timeout: int,
    insecure: bool,
    csp_report_check_url: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    result: Dict[str, Any] = {
        "ok": False,
        "pages": [],
        "errors": [],
        "csp_reports": None,
    }
    ok_all = True

    for path in pages:
        url = urljoin(base_url, path)
        try:
            resp = _fetch(url, timeout=timeout, insecure=insecure)
            csp = resp.headers.get("Content-Security-Policy")
            csp_ro = resp.headers.get("Content-Security-Policy-Report-Only")
            page_info = {
                "url": url,
                "status": resp.status_code,
                "csp": bool(csp),
                "report_only": bool(csp_ro),
            }
            result["pages"].append(page_info)

            if resp.status_code >= 400:
                ok_all = False
                result["errors"].append(f"{url} returned HTTP {resp.status_code}")

            if require_enforce:
                if not csp:
                    ok_all = False
                    result["errors"].append(
                        f"{url} missing Content-Security-Policy header (enforce required)"
                    )
                if csp_ro:
                    ok_all = False
                    result["errors"].append(
                        f"{url} returned Report-Only header while enforce is required"
                    )
        except Exception as e:
            ok_all = False
            result["errors"].append(f"{url} exception: {e}")

    # Optional CSP report counter check (expects JSON with {"count": 0})
    if csp_report_check_url:
        try:
            r = _fetch(csp_report_check_url, timeout=timeout, insecure=insecure)
            data = r.json()
            count = int(data.get("count", 0))
            result["csp_reports"] = count
            if count > 0:
                ok_all = False
                result["errors"].append(f"CSP reports present: count={count}")
        except Exception as e:
            ok_all = False
            result["errors"].append(f"CSP report check failed: {e}")

    result["ok"] = ok_all
    return ok_all, result


def _parse_set_cookie_from_raw(resp: requests.Response) -> List[str]:
    # requests keeps only the last header in resp.headers; use raw.headers.getlist to fetch all
    try:
        return list(resp.raw.headers.getlist("Set-Cookie"))
    except Exception:
        # Fallback: single header if available
        val = resp.headers.get("Set-Cookie")
        return [val] if val else []


def _cookie_has_attr(cookie_str: str, attr: str) -> bool:
    parts = [p.strip() for p in cookie_str.split(";")]
    for p in parts[1:]:
        if p.lower() == attr.lower() or p.lower().startswith(attr.lower() + "="):
            return True
    return False


def _cookie_has_no_domain(cookie_str: str) -> bool:
    parts = [p.strip().lower() for p in cookie_str.split(";")]
    return not any(p.startswith("domain=") for p in parts)


def check_host_cookies(
    url: str,
    method: str,
    body: Optional[Dict[str, Any]],
    timeout: int,
    insecure: bool,
    expected_names: Tuple[str, str] = ("__Host-pp_refresh", "__Host-pp_realm"),
) -> Tuple[bool, Dict[str, Any]]:
    result: Dict[str, Any] = {"ok": False, "url": url, "found": [], "errors": []}
    try:
        resp = _fetch(
            url,
            method=method,
            timeout=timeout,
            insecure=insecure,
            json_body=body,
            stream=True,
        )
        setcookies = _parse_set_cookie_from_raw(resp)
        result["found"] = setcookies

        # Require both cookies present (by name prefix)
        names_present = {name: False for name in expected_names}
        for sc in setcookies:
            for name in expected_names:
                if sc.startswith(name + "="):
                    names_present[name] = True
                    # Attribute checks
                    attrs_ok = all(
                        [
                            _cookie_has_attr(sc, "HttpOnly"),
                            _cookie_has_attr(sc, "Secure"),
                            _cookie_has_attr(sc, "SameSite=Strict"),
                            _cookie_has_attr(sc, "Path=/"),
                            _cookie_has_no_domain(sc),
                        ]
                    )
                    if not attrs_ok:
                        result["errors"].append(
                            f"Cookie {name}: missing required attributes or has Domain"
                        )
        # Missing cookies?
        for name, present in names_present.items():
            if not present:
                result["errors"].append(f"Missing cookie {name}")

        ok = len(result["errors"]) == 0
        result["ok"] = ok
        return ok, result
    except Exception as e:
        result["errors"].append(f"Exception: {e}")
        return False, result


def main() -> None:
    ap = argparse.ArgumentParser(description="CI checks for CSP, JWKS and __Host- cookies.")
    ap.add_argument(
        "--base-url",
        required=True,
        help="Base URL to check (e.g., https://clients.local)",
    )
    ap.add_argument(
        "--jwks-url",
        default=None,
        help="Override JWKS endpoint URL; defaults to <base>/.well-known/jwks.json",
    )
    ap.add_argument(
        "--rotation",
        action="store_true",
        help="Rotation mode: require >= 2 distinct JWKS kids",
    )
    ap.add_argument(
        "--csp-pages",
        default="/,/console,/dashboard",
        help="Comma-separated page paths to GET for CSP checks",
    )
    ap.add_argument(
        "--require-csp-enforce",
        action="store_true",
        default=True,
        help="Require Content-Security-Policy (enforce) and disallow Report-Only",
    )
    ap.add_argument(
        "--csp-report-check-url",
        default=None,
        help="Optional: URL returning JSON with {'count': 0} for CSP reports",
    )
    ap.add_argument(
        "--cookie-check-url",
        default=None,
        help="Optional: URL that sets __Host- cookies (e.g., an auth endpoint)",
    )
    ap.add_argument(
        "--cookie-method",
        default="GET",
        help="HTTP method for cookie check (default GET)",
    )
    ap.add_argument(
        "--cookie-body-path",
        default=None,
        help="Path to JSON file for cookie check request body",
    )
    ap.add_argument("--timeout", type=int, default=10, help="HTTP timeout seconds")
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="Allow insecure TLS (skip certificate verification)",
    )
    args = ap.parse_args()

    summary: Dict[str, Any] = {
        "base_url": args.base_url,
        "ok": False,
        "jwks": None,
        "csp": None,
        "cookies": None,
        "errors": [],
    }

    # JWKS
    jwks_ok, jwks_res = check_jwks(
        args.base_url, args.jwks_url, args.rotation, args.timeout, args.insecure
    )
    summary["jwks"] = jwks_res
    if not jwks_ok:
        summary["errors"].append("JWKS check failed")

    # CSP (headers + optional report)
    pages = [p.strip() for p in (args.csp_pages or "").split(",") if p.strip()]
    csp_ok, csp_res = check_csp_pages(
        args.base_url,
        pages,
        args.require_csp_enforce,
        args.timeout,
        args.insecure,
        args.csp_report_check_url,
    )
    summary["csp"] = csp_res
    if not csp_ok:
        summary["errors"].append("CSP checks failed")

    # Cookies (optional)
    cookies_ok = True
    cookies_res = None
    if args.cookie_check_url:
        body = None
        if args.cookie_body_path:
            try:
                with open(args.cookie_body_path, "r", encoding="utf-8") as fh:
                    body = json.load(fh)
            except Exception as e:
                cookies_ok = False
                cookies_res = {
                    "ok": False,
                    "error": f"Failed reading cookie body JSON: {e}",
                }
        if cookies_ok:
            cookies_ok, cookies_res = check_host_cookies(
                args.cookie_check_url,
                args.cookie_method,
                body,
                args.timeout,
                args.insecure,
            )
        summary["cookies"] = cookies_res
        if not cookies_ok:
            summary["errors"].append("Cookie checks failed")
    else:
        summary["cookies"] = {"ok": True, "skipped": True}

    summary["ok"] = jwks_ok and csp_ok and cookies_ok
    _json_print(summary)
    sys.exit(0 if summary["ok"] else 2)


if __name__ == "__main__":
    main()
