# accounts/urls.py
from __future__ import annotations

from django.urls import path

from .auth import LoginCookieView, LogoutCookieView, RefreshCookieView, WhoAmIView

urlpatterns = [
    path("auth/login-cookie/", LoginCookieView.as_view(), name="login_cookie"),
    path("auth/refresh-cookie/", RefreshCookieView.as_view(), name="refresh_cookie"),
    path("auth/logout-cookie/", LogoutCookieView.as_view(), name="logout_cookie"),
    path("auth/whoami/", WhoAmIView.as_view(), name="whoami"),
]
