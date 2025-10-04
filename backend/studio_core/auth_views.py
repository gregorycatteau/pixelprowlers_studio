# studio_core/auth_views.py
# -----------------------------------------------------------------------------
# Vues JWT avec throttling ScopedRateThrottle et sérialiseur enrichi.
# -----------------------------------------------------------------------------
from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from .jwt_serializers import AgentTokenObtainPairSerializer


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/token/ : throttle scope=jwt_obtain, sérialiseur enrichi."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_obtain"
    serializer_class = AgentTokenObtainPairSerializer


class ThrottledTokenRefreshView(TokenRefreshView):
    """POST /api/auth/token/refresh/ : throttle scope=jwt_refresh."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_refresh"


class ThrottledTokenVerifyView(TokenVerifyView):
    """POST /api/auth/token/verify/ : throttle scope=jwt_verify."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_verify"
