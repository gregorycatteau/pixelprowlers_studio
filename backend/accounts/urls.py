"""Accounts URL configuration.

Exposes endpoints:
- Cookie auth (legacy): /auth/login-cookie/, /auth/refresh-cookie/, /auth/logout-cookie/, /auth/whoami/
- Admin Dojo (WebAuthn): /auth/webauthn/options/, /auth/webauthn/verify/, /auth/nonce/, /auth/nonce/verify/
- Clients (TOTP 2FA): /auth/login/, /auth/totp/bootstrap/, /auth/totp/activate/, /auth/totp/verify/

Notes:
- JWT per realm (RS256), refresh rotation + blacklist; HttpOnly cookies (pp_refresh, pp_realm).
"""

from __future__ import annotations

from django.urls import path
from eotp.passphrase_views import api_auth_eotp_passphrase_set, api_auth_eotp_passphrase_verify

from .auth import (
    LoginCookieView,
    LogoutCookieView,
    RefreshCookieView,
    WhoAmIView,
    api_auth_eotp_gate_issue,
    api_auth_eotp_gate_verify,
    api_auth_eotp_peek,
    api_auth_eotp_resend,
    api_auth_eotp_verify,
    api_auth_login,
    api_auth_nonce,
    api_auth_nonce_verify,
    api_auth_totp_activate,
    api_auth_totp_bootstrap,
    api_auth_totp_recovery_export,
    api_auth_totp_recovery_regenerate,
    api_auth_totp_revoke,
    api_auth_totp_verify,
    api_auth_webauthn_options,
    api_auth_webauthn_verify,
)

urlpatterns = [
    path("auth/login-cookie/", LoginCookieView.as_view(), name="login_cookie"),
    path("auth/refresh-cookie/", RefreshCookieView.as_view(), name="refresh_cookie"),
    path("auth/logout-cookie/", LogoutCookieView.as_view(), name="logout_cookie"),
    path("auth/whoami/", WhoAmIView.as_view(), name="whoami"),
    path("auth/webauthn/options/", api_auth_webauthn_options, name="auth_webauthn_options"),
    path("auth/webauthn/verify/", api_auth_webauthn_verify, name="auth_webauthn_verify"),
    path("auth/nonce/", api_auth_nonce, name="auth_nonce"),
    path("auth/nonce/verify/", api_auth_nonce_verify, name="auth_nonce_verify"),
    path("auth/login/", api_auth_login, name="auth_login"),
    path("auth/totp/bootstrap/", api_auth_totp_bootstrap, name="auth_totp_bootstrap"),
    path("auth/totp/activate/", api_auth_totp_activate, name="auth_totp_activate"),
    path("auth/totp/verify/", api_auth_totp_verify, name="auth_totp_verify"),
    path("auth/2fa/email/verify/", api_auth_eotp_verify, name="auth_eotp_verify"),
    path("auth/2fa/email/resend/", api_auth_eotp_resend, name="auth_eotp_resend"),
    path("auth/2fa/email/_peek/", api_auth_eotp_peek, name="auth_eotp_peek"),
    path("auth/2fa/gate/issue/", api_auth_eotp_gate_issue, name="auth_eotp_gate_issue"),
    path("auth/2fa/gate/verify/", api_auth_eotp_gate_verify, name="auth_eotp_gate_verify"),
    path("auth/2fa/passphrase/set/", api_auth_eotp_passphrase_set, name="auth_eotp_passphrase_set"),
    path(
        "auth/2fa/passphrase/verify/",
        api_auth_eotp_passphrase_verify,
        name="auth_eotp_passphrase_verify",
    ),
    path(
        "auth/totp/recovery/export/",
        api_auth_totp_recovery_export,
        name="auth_totp_recovery_export",
    ),
    path("auth/totp/revoke/", api_auth_totp_revoke, name="auth_totp_revoke"),
    path(
        "auth/totp/recovery/regenerate/",
        api_auth_totp_recovery_regenerate,
        name="auth_totp_recovery_regenerate",
    ),
]
