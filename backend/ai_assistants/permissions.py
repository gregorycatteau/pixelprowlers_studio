from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import ValidationError

from .security import NonceError, RequestNonce


class RequireSignedNonce(permissions.BasePermission):
    """
    Ensure that mutating requests include a valid X-Request-Nonce header.
    """

    message = "nonce_missing"

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True

        nonce = request.headers.get("X-Request-Nonce") or request.META.get("HTTP_X_REQUEST_NONCE")
        try:
            RequestNonce.validate(nonce, getattr(request.user, "pk", None))
        except NonceError as exc:
            raise ValidationError({"error": exc.code})
        return True
