# backend/ai_assistants/admin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    AgentProfile,
    AgentRun,
    AgentToolCall,
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
    DailyBudget,
    DojoAgent,
)
from .utils.agent_schema import compute_manifest_hash, validate_agent_profile

# ============================================================================
# Helpers compat champs (is_enabled vs is_active)
# ============================================================================


def _has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


class EnabledFilter(admin.SimpleListFilter):
    title = "Activé"
    parameter_name = "enabled"

    def lookups(self, request, model_admin):
        return (("1", "Oui"), ("0", "Non"))

    def queryset(self, request, queryset):
        val = self.value()
        if val not in ("1", "0"):
            return queryset
        want_true = val == "1"
        Model = queryset.model
        if _has_field(Model, "is_enabled"):
            return queryset.filter(is_enabled=want_true)
        if _has_field(Model, "is_active"):
            return queryset.filter(is_active=want_true)
        return queryset.none() if want_true else queryset


class PremiumUnlockedFilter(admin.SimpleListFilter):
    title = "Premium déverrouillé"
    parameter_name = "premium"

    def lookups(self, request, model_admin):
        return (("1", "Oui"), ("0", "Non"))

    def queryset(self, request, queryset):
        val = self.value()
        if val not in ("1", "0"):
            return queryset
        want_true = val == "1"
        Model = queryset.model
        if _has_field(Model, "is_premium_unlocked"):
            return queryset.filter(is_premium_unlocked=want_true)
        # champ absent → traiter comme toujours False
        return queryset.none() if want_true else queryset


# ============================================================================
# Inlines
# ============================================================================


class AgentToolCallInline(admin.TabularInline):
    model = AgentToolCall
    extra = 0
    can_delete = False
    readonly_fields = ("name", "success", "short_args", "short_result", "created_at")
    fields = ("name", "success", "short_args", "short_result", "created_at")

    def short_args(self, obj):
        s = str(obj.args)[:120]
        return s + ("…" if len(str(obj.args)) > 120 else "")

    short_args.short_description = "Args"

    def short_result(self, obj):
        s = str(obj.result)[:120]
        return s + ("…" if len(str(obj.result)) > 120 else "")

    short_result.short_description = "Résultat"


# ============================================================================
# AgentProfile
# ============================================================================


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    """
    Administration des profils d'agents (manifestes v2.1).
    - Validation schéma + hash manifeste
    - Monitoring budget jour restant
    - Actions utiles (activer/désactiver, lock/unlock premium, revalider)
    """

    list_display = (
        "slug",
        "name",
        "alias",
        "profile_version",
        "schema_version",
        "enabled",
        "premium_unlocked",  # ← méthodes robustes
        "spent_today_eur",
        "remaining_today_eur",
        "updated_at",
    )
    list_filter = (EnabledFilter, PremiumUnlockedFilter, "schema_version", "profile_version")
    search_fields = ("slug", "name", "alias", "description")
    readonly_fields = (
        "schema_version",
        "profile_version",
        "manifest_hash_sha256",
        "preview_manifest",
        "spent_today_eur",
        "remaining_today_eur",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("Identité", {"fields": ("slug", "name", "alias", "description")}),
        (
            "Manifeste (source de vérité)",
            {
                "fields": (
                    "manifest_json",
                    "preview_manifest",
                    "schema_version",
                    "profile_version",
                    "manifest_hash_sha256",
                )
            },
        ),
        (
            "État",
            {
                # champs affichés si présents, sinon juste l’aperçu des méthodes
                "fields": tuple(
                    [
                        f
                        for f in ("is_enabled", "is_active", "is_premium_unlocked")
                        if _has_field(AgentProfile, f)
                    ]
                )
                or tuple()
            },
        ),
        ("Budget (aujourd'hui)", {"fields": ("spent_today_eur", "remaining_today_eur")}),
        ("Horodatage", {"fields": ("created_at", "updated_at")}),
    )
    actions = [
        "action_enable",
        "action_disable",
        "action_unlock_premium",
        "action_lock_premium",
        "action_revalidate",
    ]

    # --- Colonnes dynamiques ---
    def enabled(self, obj: AgentProfile) -> bool:
        if _has_field(AgentProfile, "is_enabled"):
            return bool(getattr(obj, "is_enabled", False))
        return bool(getattr(obj, "is_active", False))

    enabled.boolean = True
    enabled.short_description = "Activé"

    def premium_unlocked(self, obj: AgentProfile) -> bool:
        return bool(getattr(obj, "is_premium_unlocked", False))

    premium_unlocked.boolean = True
    premium_unlocked.short_description = "Premium"

    # --- KPIs budget jour ---
    def spent_today_eur(self, obj: AgentProfile) -> str:
        return f"{obj.spent_today():.4f} €"

    spent_today_eur.short_description = "Dépensé aujourd’hui"

    def remaining_today_eur(self, obj: AgentProfile) -> str:
        return f"{obj.remaining_today():.4f} €"

    remaining_today_eur.short_description = "Restant aujourd’hui"

    # --- Aperçu manifeste ---
    def preview_manifest(self, obj: AgentProfile) -> str:
        raw = obj.manifest_json or {}
        s = str(raw)
        s = (s[:800] + "…") if len(s) > 800 else s
        return format_html("<code style='white-space:pre-wrap;font-size:12px'>{}</code>", s)

    preview_manifest.short_description = "Aperçu manifeste"

    # --- Actions ---
    @admin.action(description="✅ Activer les agents sélectionnés")
    def action_enable(self, request, queryset):
        Model = queryset.model
        updated = 0
        if _has_field(Model, "is_enabled"):
            updated = queryset.update(is_enabled=True)
        elif _has_field(Model, "is_active"):
            updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} agent(s) activé(s).", messages.SUCCESS)

    @admin.action(description="⛔ Désactiver les agents sélectionnés")
    def action_disable(self, request, queryset):
        Model = queryset.model
        updated = 0
        if _has_field(Model, "is_enabled"):
            updated = queryset.update(is_enabled=False)
        elif _has_field(Model, "is_active"):
            updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} agent(s) désactivé(s).", messages.WARNING)

    @admin.action(description="🔓 Déverrouiller l'usage premium")
    def action_unlock_premium(self, request, queryset):
        if _has_field(queryset.model, "is_premium_unlocked"):
            updated = queryset.update(is_premium_unlocked=True)
            self.message_user(
                request, f"{updated} agent(s) premium déverrouillé(s).", messages.SUCCESS
            )
        else:
            self.message_user(
                request, "Champ 'is_premium_unlocked' absent sur ce schéma.", messages.INFO
            )

    @admin.action(description="🔒 Verrouiller l'usage premium")
    def action_lock_premium(self, request, queryset):
        if _has_field(queryset.model, "is_premium_unlocked"):
            updated = queryset.update(is_premium_unlocked=False)
            self.message_user(request, f"{updated} agent(s) premium verrouillé(s).", messages.INFO)
        else:
            self.message_user(
                request, "Champ 'is_premium_unlocked' absent sur ce schéma.", messages.INFO
            )

    @admin.action(description="🧪 Revalider manifeste (schéma + hash)")
    def action_revalidate(self, request, queryset):
        ok, ko = 0, 0
        for agent in queryset:
            errors = validate_agent_profile(agent.manifest_json or {})
            if errors:
                ko += 1
                self.message_user(
                    request, f"[{agent.slug}] erreurs schéma: {errors}", messages.ERROR
                )
                continue
            agent.manifest_hash_sha256 = compute_manifest_hash(agent.manifest_json or {})
            agent.save(update_fields=["manifest_hash_sha256", "updated_at"])
            ok += 1
        if ok:
            self.message_user(request, f"{ok} manifeste(s) revalidé(s).", messages.SUCCESS)
        if ko and not ok:
            self.message_user(request, "Aucun manifeste revalidé (erreurs).", messages.ERROR)


# ============================================================================
# AgentRun
# ============================================================================


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    """Journal des exécutions (LLM)."""

    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "agent",
        "provider",
        "model",
        "status_colored",
        "cost_eur",
        "tokens_in",
        "tokens_out",
        "latency_ms",
        "short_input",
        "short_output",
    )
    list_filter = ("agent", "provider", "model", "status", "created_at")
    search_fields = ("input_excerpt", "output_excerpt", "error_message", "correlation_id")
    readonly_fields = (
        "agent",
        "provider",
        "model",
        "started_at",
        "finished_at",
        "tokens_in",
        "tokens_out",
        "latency_ms",
        "cost_eur",
        "input_excerpt",
        "output_excerpt",
        "status",
        "error_message",
        "created_at",
    )
    inlines = [AgentToolCallInline]
    list_per_page = 25
    ordering = ("-created_at",)

    def status_colored(self, obj):
        palette = {
            "success": "#198754",
            "error": "#dc3545",
            "blocked": "#fd7e14",
            "rate_limited": "#0dcaf0",
        }
        return format_html(
            "<b style='color:{}'>{}</b>", palette.get(obj.status, "#6c757d"), obj.status
        )

    status_colored.short_description = "Statut"

    def short_input(self, obj):
        s = obj.input_excerpt or ""
        return s[:60] + ("…" if len(s) > 60 else "")

    short_input.short_description = "Entrée"

    def short_output(self, obj):
        s = obj.output_excerpt or ""
        return s[:60] + ("…" if len(s) > 60 else "")

    short_output.short_description = "Sortie"


# ============================================================================
# DailyBudget
# ============================================================================


@admin.register(DailyBudget)
class DailyBudgetAdmin(admin.ModelAdmin):
    """Agrégats budgétaires quotidien par agent."""

    date_hierarchy = "date"
    list_display = (
        "date",
        "agent",
        "spent_eur",
        "cap_eur",
        "over_cap_badge",
        "tokens_in",
        "tokens_out",
    )
    list_filter = ("agent", "date")
    search_fields = ("agent__slug",)
    readonly_fields = ("date", "agent", "spent_eur", "tokens_in", "tokens_out")

    def cap_eur(self, obj):
        return f"{obj.agent.budget_max_eur_per_day():.4f}"

    cap_eur.short_description = "Cap €/jour"

    def over_cap_badge(self, obj):
        cap = obj.agent.budget_max_eur_per_day()
        over = (obj.spent_eur or Decimal("0")) > cap if cap else False
        color = "#dc3545" if over else "#198754"
        label = "DÉPASSÉ" if over else "OK"
        return format_html("<b style='color:{}'>{}</b>", color, label)

    over_cap_badge.short_description = "Budget"


# ============================================================================
# Dojo Conversations (read-only)
# ============================================================================


@admin.register(DojoAgent)
class DojoAgentAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("slug", "title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "agent", "creator", "status", "created_at", "updated_at")
    list_filter = ("status", "agent")
    search_fields = ("id", "title", "creator__username", "agent__slug")
    readonly_fields = ("meta", "created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("agent", "creator")


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("id", "conversation__id", "content")
    readonly_fields = ("conversation", "role", "content", "tokens", "meta", "created_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("conversation", "conversation__agent")


@admin.register(ConversationAuditLog)
class ConversationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "object_type", "object_id", "actor")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__username", "ip_address", "action")
    readonly_fields = (
        "actor",
        "action",
        "object_type",
        "object_id",
        "ip_address",
        "user_agent",
        "extra",
        "created_at",
    )
