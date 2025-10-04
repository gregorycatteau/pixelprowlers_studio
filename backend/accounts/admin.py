from __future__ import annotations

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.http import HttpRequest

from .models import AgentProfile, AuditLog


class SecureAdminSite(AdminSite):
    """
    AdminSite qui refuse l'accès aux comptes agents (is_agent=True),
    même s'ils sont 'is_staff=True'. Les owners (superusers) passent.
    """

    site_header = "Administration PixelProwlers"
    site_title = "Admin PixelProwlers"

    def has_permission(self, request: HttpRequest) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        # Bloque l'admin si le compte est un agent IA
        try:
            if user.agent_profile:
                return False
        except Exception:
            pass
        return user.is_staff


admin_site = SecureAdminSite(name="secure_admin")


@admin.register(AgentProfile, site=admin_site)
class AgentProfileAdmin(admin.ModelAdmin):
    """Admin pour visualiser/filtrer rapidement les agents."""

    list_display = ("user", "label", "is_active", "created_by", "created_at")
    list_filter = ("is_active", "created_by")
    search_fields = ("user__username", "label")
    readonly_fields = ("created_at",)


@admin.register(AuditLog, site=admin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "username",
        "is_agent",
        "method",
        "path",
        "status_code",
        "jwt_jti",
    )
    list_filter = ("status_code", "is_agent", "method")
    search_fields = ("username", "path", "jwt_jti")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
