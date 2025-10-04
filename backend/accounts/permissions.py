from __future__ import annotations

from typing import Iterable, Set

from rest_framework.permissions import BasePermission


def _get_token_payload(request) -> dict:
    """
    Récupère le payload JWT tel que parsé par SimpleJWT (request.auth.payload).
    """
    token = getattr(request, "auth", None)
    if token and hasattr(token, "payload"):
        return token.payload or {}
    return {}


def _token_scopes(request) -> Set[str]:
    """
    Extrait les scopes (set[str]) depuis le JWT.
    """
    payload = _get_token_payload(request)
    scopes = payload.get("scopes", [])
    if isinstance(scopes, Iterable):
        return set(scopes)
    return set()


class IsOwnerOrScopedStaff(BasePermission):
    """
    Autorise si :
    - superuser => accès total
    - OU (is_staff=True) + tous les 'required_scopes' définis sur la vue.

    Usage:
        class MyView(...):
            permission_classes = [IsOwnerOrScopedStaff]
            required_scopes = {"articles:read"}  # à définir sur la vue
    """

    message = "Accès refusé : privilèges insuffisants."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        required = getattr(view, "required_scopes", set())
        if not required:
            return True
        return required.issubset(_token_scopes(request))


class ObjectOwnerOrScopedWrite(BasePermission):
    """
    Autorise l'écriture si :
    - superuser
    - propriétaire de l'objet (obj.owner == request.user)
    - staff avec tous les 'required_write_scopes'

    Usage:
        class MyView(...):
            permission_classes = [IsOwnerOrScopedStaff, ObjectOwnerOrScopedWrite]
            required_write_scopes = {"articles:write"}
    """

    message = "Accès objet refusé : propriétaire ou scope d'écriture requis."

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if hasattr(obj, "owner_id") and obj.owner_id == user.id:
            return True
        required = getattr(view, "required_write_scopes", set())
        return required.issubset(_token_scopes(request))
