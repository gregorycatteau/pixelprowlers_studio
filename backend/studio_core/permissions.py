# studio_core/permissions.py
# -----------------------------------------------------------------------------
# Permissions Strawberry basées sur des "scopes" (JWT/AgentProfile).
# - scope_perm("scope:clé")   -> exige TOUS les scopes fournis.
# - any_scope_perm("a","b")   -> exige AU MOINS UN des scopes fournis.
# - Bypass optionnel (break-glass): ALLOW_BYPASS_SUPERUSER=true -> is_superuser autorisé.
#   ⚠️ à n'utiliser qu'en dev/incident (journalisation incluse).
# -----------------------------------------------------------------------------
from __future__ import annotations

import logging
import os
from typing import Iterable, Set

from strawberry.permission import BasePermission

logger = logging.getLogger(__name__)

# Flag de secours (par défaut: False)
_ALLOW_BYPASS_SUPERUSER = os.getenv("ALLOW_BYPASS_SUPERUSER", "false").lower() in (
    "1",
    "true",
    "yes",
)


def _collect_scopes_from_request(request) -> Set[str]:
    """
    Extrait les scopes du request courant :
    - d'abord depuis le JWT (token.payload['scopes'] si présent),
    - puis depuis l'AgentProfile actif (défense en profondeur).
    """
    scopes: Set[str] = set()

    # Scopes JWT (Authorization: Bearer ...)
    token = getattr(request, "auth", None)
    if token is not None and hasattr(token, "payload"):
        try:
            scopes.update(token.payload.get("scopes", []) or [])
        except Exception:
            pass

    # Scopes DB (AgentProfile actif)
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        try:
            from accounts.models import AgentProfile  # import tardif (évite cycles)

            ap = AgentProfile.objects.filter(user=user, is_active=True).only("scopes").first()
            if ap and ap.scopes:
                scopes.update(ap.scopes)
        except Exception:
            pass

    return scopes


class RequireScopes(BasePermission):
    """
    Permission Strawberry paramétrable qui exige un ensemble de scopes.
    À utiliser via les factories scope_perm()/any_scope_perm().
    """

    required: Iterable[str] = ()
    mode: str = "all"  # 'all' ou 'any'
    message = "Accès refusé : scope(s) manquant(s)."

    def has_permission(self, source, info, **kwargs) -> bool:  # type: ignore[override]
        request = info.context.request
        user = getattr(request, "user", None)

        # Break-glass (usage consigné)
        if _ALLOW_BYPASS_SUPERUSER and getattr(user, "is_superuser", False):
            logger.warning(
                "BYPASS_USED: superuser bypass for GraphQL scope check",
                extra={
                    "user": getattr(user, "username", None),
                    "scopes_required": list(self.required or []),
                },
            )
            return True

        if not getattr(user, "is_authenticated", False):
            return False

        # Owners => accès total
        if getattr(user, "is_superuser", False):
            return True

        # Agents/staff uniquement pour les scopes API
        if not getattr(user, "is_staff", False):
            return False

        got = _collect_scopes_from_request(request)
        req = set(self.required or [])
        if not req:
            return True

        if self.mode == "any":
            return bool(got & req)
        # default: 'all'
        return req.issubset(got)


def scope_perm(*scopes: str):
    """
    Fabrique une CLASSE de permission exigeant TOUS les scopes fournis.
    Usage :
        @strawberry.mutation(permission_classes=[scope_perm("agents:analyze_schema")])
    """

    class _RequireAll(RequireScopes):
        required = scopes
        mode = "all"
        message = f"Accès refusé : scopes requis ({', '.join(scopes)})."

    return _RequireAll


def any_scope_perm(*scopes: str):
    """
    Fabrique une CLASSE de permission exigeant AU MOINS UN des scopes fournis.
    Usage :
        @strawberry.field(permission_classes=[any_scope_perm("a:read","b:read")])
    """

    class _RequireAny(RequireScopes):
        required = scopes
        mode = "any"
        message = f"Accès refusé : au moins un des scopes requis ({', '.join(scopes)})."

    return _RequireAny
