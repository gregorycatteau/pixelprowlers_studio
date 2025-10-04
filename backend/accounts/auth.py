# accounts/auth.py
# -----------------------------------------------------------------------------
# Auth JWT + cookies (refresh HttpOnly) pour PixelProwlers Studio
# - Serializer custom: ajoute username/is_staff/is_superuser/scopes dans le JWT
# - Endpoints:
#     POST /api/accounts/auth/login-cookie/    -> set cookie refresh + retourne access
#     POST /api/accounts/auth/refresh-cookie/  -> lit cookie refresh, rotate + retourne access
#     POST /api/accounts/auth/logout-cookie/   -> blacklist (si activé) + clear cookie
#     GET  /api/accounts/auth/whoami/          -> infos de l'utilisateur courant
# - En dev (DEBUG=True): CSRF relaxé pour simplifier les tests sur refresh/logout.
#   En prod: on exige X-CSRFToken == cookie "csrftoken" (double-submit cookie).
# - Cette version attrape toute exception et renvoie du JSON (plus de page HTML).
# -----------------------------------------------------------------------------
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.middleware.csrf import get_token as get_csrf_token
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)

# Blacklist (si app installée)
try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken  # noqa: F401

    _HAS_BLACKLIST = True
except Exception:
    _HAS_BLACKLIST = False


# =========================
# Serializer personnalisé
# =========================
class PPTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Ajoute des claims utiles dans le JWT (access & refresh)."""

    @classmethod
    def get_token(cls, user):
        """
        Retourne un RefreshToken (qui porte .access) enrichi de quelques claims.
        """
        token = super().get_token(user)

        # Claims baseline (ne rien mettre de sensible)
        token["username"] = user.get_username()
        token["is_staff"] = bool(getattr(user, "is_staff", False))
        token["is_superuser"] = bool(getattr(user, "is_superuser", False))

        # Scopes depuis AgentProfile actif (défense en profondeur)
        scopes = []
        try:
            ap = getattr(user, "agent_profile", None)
            if ap and getattr(ap, "is_active", False):
                scopes = list(ap.scopes or [])
        except Exception:
            scopes = []
        token["scopes"] = scopes
        return token

    def validate(self, attrs):
        """
        Laisse SimpleJWT faire l'auth, puis met à jour last_login si activé.
        """
        data = super().validate(attrs)
        # On laisse UPDATE_LAST_LOGIN à SimpleJWT via settings; pas d'autre logique ici.
        return data


class PPTokenObtainPairView(TokenObtainPairView):
    """Optionnel : /api/auth/token/ branché sur le serializer custom."""

    serializer_class = PPTokenObtainPairSerializer
    throttle_scope = "jwt_obtain"


# =========================
# Helpers cookies & CSRF
# =========================
REFRESH_COOKIE_NAME = getattr(settings, "PP_REFRESH_COOKIE_NAME", "pp_refresh")
REFRESH_COOKIE_PATH = getattr(settings, "PP_REFRESH_COOKIE_PATH", "/")
REFRESH_COOKIE_SECURE = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
REFRESH_COOKIE_SAMESITE = getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax"
REFRESH_COOKIE_DOMAIN = getattr(settings, "SESSION_COOKIE_DOMAIN", None)
# NOTE: SimpleJWT attend un timedelta ; on convertit en secondes pour max_age.
REFRESH_TOKEN_LIFETIME: timedelta = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


def _set_refresh_cookie(resp: Response, refresh_token: str) -> None:
    """Place le refresh token dans un cookie HttpOnly."""
    resp.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        domain=REFRESH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
        max_age=int(REFRESH_TOKEN_LIFETIME.total_seconds()),
    )


def _clear_refresh_cookie(resp: Response) -> None:
    resp.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        domain=REFRESH_COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
    )


def _require_csrf(request) -> bool:
    """
    En prod: exige X-CSRFToken == cookie csrftoken (double-submit).
    En dev: relax (retourne True).
    """
    if settings.DEBUG:
        return True
    header = request.META.get("HTTP_X_CSRFTOKEN")
    cookie = request.COOKIES.get("csrftoken")
    return bool(header and cookie and header == cookie)


# =========================
# Vues cookies (robustes)
# =========================
class LoginCookieView(APIView):
    """
    Authentifie l’utilisateur et:
    - set cookie refresh HttpOnly
    - retourne l'access token en JSON + quelques infos user (non sensibles)
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_obtain"

    def get(self, request, *args, **kwargs):
        """
        GET optionnel: permet de pré-déposer un csrftoken côté front (utile en prod).
        """
        try:
            resp = Response({"detail": "OK"}, status=status.HTTP_200_OK)
            csrft = get_csrf_token(request)
            resp.set_cookie(
                "csrftoken",
                csrft,
                secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
                samesite=getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax",
                domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
                path="/",
                httponly=False,
            )
            return resp
        except Exception as e:
            logger.exception("LoginCookieView.GET failed")
            return Response(
                {"detail": "login_cookie_get_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, *args, **kwargs):
        """
        POST: username/password -> JSON {access, user{...}} + cookie refresh HttpOnly.
        """
        try:
            ser = PPTokenObtainPairSerializer(data=request.data)
            ser.is_valid(raise_exception=True)

            access = ser.validated_data["access"]
            refresh = ser.validated_data["refresh"]
            user = ser.user

            payload = {
                "access": access,
                "user": {
                    "username": user.get_username(),
                    "is_staff": bool(user.is_staff),
                    "is_superuser": bool(user.is_superuser),
                },
            }
            resp = Response(payload, status=status.HTTP_200_OK)

            # Cookie refresh HttpOnly
            _set_refresh_cookie(resp, refresh)

            # Dépose/renouvelle aussi le csrftoken (utile pour refresh/logout en prod)
            try:
                csrft = get_csrf_token(request)
                resp.set_cookie(
                    "csrftoken",
                    csrft,
                    secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
                    samesite=getattr(settings, "CSRF_COOKIE_SAMESITE", "Lax") or "Lax",
                    domain=getattr(settings, "SESSION_COOKIE_DOMAIN", None),
                    path="/",
                    httponly=False,
                )
            except Exception:
                # non bloquant
                pass

            return resp

        except (ValidationError, AuthenticationFailed) as e:
            # Identifiants invalides → 401 JSON
            return Response(
                {"detail": "bad_credentials", "errors": getattr(e, "detail", str(e))},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.exception("LoginCookieView.POST failed")
            return Response(
                {"detail": "login_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RefreshCookieView(APIView):
    """
    Lit le refresh token depuis le cookie HttpOnly, vérifie/rotate/blacklist,
    renvoie un nouvel access token et réécrit le cookie refresh si rotation.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_refresh"

    def post(self, request, *args, **kwargs):
        try:
            if not _require_csrf(request):
                return Response({"detail": "CSRF check failed"}, status=status.HTTP_403_FORBIDDEN)

            raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
            if not raw:
                return Response(
                    {"detail": "No refresh cookie"}, status=status.HTTP_401_UNAUTHORIZED
                )

            try:
                refresh = RefreshToken(raw)
            except TokenError as e:
                return Response(
                    {"detail": f"Invalid refresh token: {e}"}, status=status.HTTP_401_UNAUTHORIZED
                )

            access = str(refresh.access_token)

            rotate = bool(settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS", False))
            blacklist_after = bool(settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION", False))
            resp = Response({"access": access}, status=status.HTTP_200_OK)

            if rotate:
                try:
                    new_refresh = refresh.rotate()
                    if blacklist_after and _HAS_BLACKLIST:
                        try:
                            refresh.blacklist()
                        except Exception:
                            pass
                    _set_refresh_cookie(resp, str(new_refresh))
                except Exception as e:
                    return Response(
                        {"detail": f"Cannot rotate: {e}"}, status=status.HTTP_400_BAD_REQUEST
                    )

            return resp

        except Exception as e:
            logger.exception("RefreshCookieView.POST failed")
            return Response(
                {"detail": "refresh_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogoutCookieView(APIView):
    """
    Invalide (blacklist si dispo) le refresh en cookie, puis le supprime.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "jwt_refresh"

    def post(self, request, *args, **kwargs):
        try:
            if not _require_csrf(request):
                return Response({"detail": "CSRF check failed"}, status=status.HTTP_403_FORBIDDEN)

            raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
            resp = Response({"detail": "logged out"}, status=status.HTTP_200_OK)

            if raw:
                try:
                    token = RefreshToken(raw)
                    if _HAS_BLACKLIST:
                        try:
                            token.blacklist()
                        except Exception:
                            pass
                except TokenError:
                    pass

            _clear_refresh_cookie(resp)
            return resp

        except Exception as e:
            logger.exception("LogoutCookieView.POST failed")
            return Response(
                {"detail": "logout_cookie_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WhoAmIView(APIView):
    """
    Retourne des infos minimales sur l'utilisateur courant (JWT access requis).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user = request.user
            scopes = []
            try:
                ap = getattr(user, "agent_profile", None)
                if ap and getattr(ap, "is_active", False):
                    scopes = list(ap.scopes or [])
            except Exception:
                pass

            return Response(
                {
                    "username": user.get_username(),
                    "is_staff": bool(user.is_staff),
                    "is_superuser": bool(user.is_superuser),
                    "scopes": scopes,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("WhoAmIView.GET failed")
            return Response(
                {"detail": "whoami_failed", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
