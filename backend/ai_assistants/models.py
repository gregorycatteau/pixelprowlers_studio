# backend/ai_assistants/models.py
# -*- coding: utf-8 -*-
"""
Modèles de l'app ai_assistants (v2.1 fusion)
- AgentProfile : manifeste JSON (schéma v2.1), hash et champs dérivés (compat admin/serializer).
- AgentRun : journalise une exécution LLM (provider, modèle, tokens, coût, statut).
- AgentToolCall : trace l'utilisation d'un outil (nom, args, résultat).
- DailyBudget : cumule les coûts/jour par agent pour faire respecter la politique budgétaire.
- Manifesto / AgentSystemContext / AgentMessageLog / AgentImpactReport / JaredLog : conformité admin/signaux existants.
- UserSecurityProfile : secrets d’auth “préflight” (teinte + ordre d’émojis + sandbox).
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from .utils.agent_schema import (
    SCHEMA_VERSION,
    compute_manifest_hash,
    ensure_immutable_fields_unchanged,
    validate_agent_profile,
)

# ──────────────────────────────────────────────────────────────────────────────
# Utils locaux
# ──────────────────────────────────────────────────────────────────────────────


def local_today() -> date_type:
    """
    Retourne la date locale du jour (timezone Django).
    Utile pour agréger le budget quotidien.
    """
    return timezone.localdate()


def first_chars(txt: Optional[str], n: int = 512) -> str:
    """
    Renvoie un extrait tronqué (safe) d'un texte pour stockage rapide.
    """
    if not txt:
        return ""
    t = str(txt)
    return t if len(t) <= n else t[:n] + "…"


# ──────────────────────────────────────────────────────────────────────────────
# Modèles "agents" (v2.1, compat admin)
# ──────────────────────────────────────────────────────────────────────────────


class AgentProfile(models.Model):
    """
    Profil d'agent aligné sur le schéma v2.1 (manifest JSON).
    - Le JSON est validé et haché à l'enregistrement.
    - Certains champs immuables sont contrôlés (identity.slug / tools[].name).
    - Champs dérivés pour compat (model / temperature / is_active / communication_style).
    """

    # Identité / clés rapides
    slug = models.SlugField(
        unique=True, help_text="Identifiant court (ex: 'jared', 'claire'). Immuable après création."
    )
    name = models.CharField(max_length=120, help_text="Nom d'affichage de l'agent.")
    alias = models.CharField(
        max_length=160, blank=True, default="", help_text="Alias/verbe métier."
    )
    description = models.TextField(blank=True, default="", help_text="Résumé fonctionnel.")

    # Versions & manifeste
    schema_version = models.CharField(max_length=16, default=SCHEMA_VERSION, editable=False)
    profile_version = models.CharField(
        max_length=16, default="2.1.0", help_text="Semver du profil."
    )
    manifest_json = models.JSONField(help_text="Manifeste complet v2.1 validé (source de vérité).")
    manifest_hash_sha256 = models.CharField(max_length=64, blank=True, default="", editable=False)

    # Champs dérivés (compat admin/front)
    model = models.CharField(
        max_length=128, default="gpt-4o", help_text="Cache dérivé du manifeste."
    )
    temperature = models.FloatField(default=0.4, help_text="Cache dérivé du manifeste.")
    communication_style = models.CharField(max_length=255, blank=True, default="Standard")
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil d'agent"
        verbose_name_plural = "Profils d'agents"
        ordering = ["slug"]

    def __str__(self) -> str:
        return f"{self.slug} ({self.profile_version})"

    # ── Helpers internes pour extraire des infos du manifeste ─────────────────

    def _manifest_identity(self) -> Dict[str, Any]:
        return (self.manifest_json or {}).get("identity", {}) or {}

    def _manifest_model_policy(self) -> Dict[str, Any]:
        return (self.manifest_json or {}).get("model_policy", {}) or {}

    def _manifest_runtime(self) -> Dict[str, Any]:
        # Certaines variantes stockent le choix du modèle/température dans une section runtime
        return (self.manifest_json or {}).get("runtime", {}) or {}

    def _derive_model_from_manifest(self) -> str:
        """
        Essaie d'extraire le modèle privilégié depuis le manifeste.
        Fallback sur self.model si non présent.
        """
        mp = self._manifest_model_policy()
        runtime = self._manifest_runtime()

        # Essais multiples (on reste tolérant selon la structure réelle)
        selected = (
            runtime.get("model")
            or mp.get("selected_model")
            or (mp.get("allowed_models", {}).get("premium") or [None])[0]
            or (mp.get("allowed_models", {}).get("mid") or [None])[0]
            or (mp.get("allowed_models", {}).get("local") or [None])[0]
        )
        return selected or self.model or "gpt-4o"

    def _derive_temperature_from_manifest(self) -> float:
        """
        Essaie d'extraire la température privilégiée depuis le manifeste.
        """
        runtime = self._manifest_runtime()
        if isinstance(runtime.get("temperature"), (int, float)):
            return float(runtime["temperature"])
        return float(self.temperature or 0.4)

    # ── Validation / Clean ────────────────────────────────────────────────────

    def clean(self) -> None:
        """
        Valide le manifeste JSON, l'immuabilité et met à jour hash + dérivés.
        """
        # 1) Validation schéma JSON v2.1
        errors = validate_agent_profile(self.manifest_json or {})
        if errors:
            raise ValidationError({"manifest_json": errors})

        # 2) Contrôle immuables par rapport à l'état précédent (si update)
        if self.pk:
            old: "AgentProfile" = AgentProfile.objects.get(pk=self.pk)
            immu_errors = ensure_immutable_fields_unchanged(old.manifest_json, self.manifest_json)
            if immu_errors:
                raise ValidationError({"manifest_json": immu_errors})

        # 3) Champs dérivés depuis le manifeste (source de vérité)
        ident = self._manifest_identity()
        self.name = ident.get("name", self.name)
        self.alias = ident.get("alias", self.alias)
        self.description = ident.get("description", self.description)
        self.schema_version = (self.manifest_json or {}).get("schema_version", SCHEMA_VERSION)
        self.profile_version = (self.manifest_json or {}).get(
            "profile_version", self.profile_version
        )

        # 4) Conformité du slug (manifest vs champ DB)
        manifest_slug = ident.get("slug")
        if manifest_slug and manifest_slug != self.slug:
            raise ValidationError(
                {"slug": f"slug='{self.slug}' ≠ manifest.identity.slug='{manifest_slug}'"}
            )

        # 5) Dérivés compat (model/temperature/communication_style/is_active)
        try:
            self.model = self._derive_model_from_manifest()
        except Exception:
            pass
        try:
            self.temperature = self._derive_temperature_from_manifest()
        except Exception:
            pass

        style = (self.manifest_json or {}).get("communication_style", {}) or {}
        if isinstance(style, dict):
            # Optionnel : convertir un objet en courte description
            tone = style.get("tone")
            lang = style.get("language_level")
            self.communication_style = f"{tone or 'Standard'} ({lang or '—'})".strip()
        else:
            # Ou laisser tel quel si déjà une chaîne
            self.communication_style = self.communication_style or "Standard"

        flags = (self.manifest_json or {}).get("flags", {}) or {}
        if isinstance(flags, dict) and "is_active" in flags:
            self.is_active = bool(flags.get("is_active"))

        # 6) Hash
        self.manifest_hash_sha256 = compute_manifest_hash(self.manifest_json or {})

    # --- Politique budget (lecture manifeste) ---

    def budget_max_eur_per_day(self) -> Decimal:
        """
        Lit budget_policy.max_eur_per_day depuis le manifeste.
        Retourne Decimal('0') si absent.
        """
        val = (
            (self.manifest_json or {})
            .get("model_policy", {})
            .get("budget_policy", {})
            .get("max_eur_per_day", 0.0)
        )
        try:
            return Decimal(str(val))
        except Exception:
            return Decimal("0")

    def hard_stop_on_exceed(self) -> bool:
        """
        Indique si l'on doit couper net en cas de dépassement du budget journalier.
        """
        return bool(
            (self.manifest_json or {})
            .get("model_policy", {})
            .get("budget_policy", {})
            .get("hard_stop_on_exceed", True)
        )

    # --- Agrégats de budget ---

    def spent_today(self) -> Decimal:
        """
        Somme du coût des runs 'success' du jour pour cet agent.
        """
        d = local_today()
        agg = DailyBudget.objects.filter(agent=self, date=d).first()
        return agg.spent_eur if agg else Decimal("0")

    def remaining_today(self) -> Decimal:
        """
        Budget restant pour aujourd'hui.
        """
        return max(Decimal("0"), self.budget_max_eur_per_day() - self.spent_today())

    def can_spend(self, amount_eur: Decimal) -> bool:
        """
        Vérifie si un nouvel amount_eur peut être engagé aujourd'hui.
        """
        if not self.hard_stop_on_exceed():
            return True
        return self.remaining_today() >= amount_eur


class AgentRun(models.Model):
    """
    Exécution LLM d'un agent (un "run").
    On y stocke : provider, modèle, tokens, coût estimé, latence, statut, extraits.
    """

    STATUS_CHOICES = [
        ("success", "Succès"),
        ("error", "Erreur"),
        ("blocked", "Bloqué (policy/budget)"),
        ("rate_limited", "Rate limited"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="runs")
    correlation_id = models.CharField(
        max_length=64, blank=True, default="", help_text="ID corrélatif côté API/appelant."
    )

    # Provider / modèle
    provider = models.CharField(max_length=64, help_text="openai|anthropic|ollama|…")
    model = models.CharField(max_length=128, help_text="gpt-4o-mini|claude-3.7-haiku|llama3:8b|…")

    # Chrono
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Compteurs
    tokens_in = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    tokens_out = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    latency_ms = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    # Coût estimé (calculé par la couche service, arrondi 1/10000 €)
    cost_eur = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0.0000"))

    # I/O (extraits)
    input_excerpt = models.TextField(blank=True, default="")
    output_excerpt = models.TextField(blank=True, default="")

    # Statut
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="success")
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Exécution d'agent"
        verbose_name_plural = "Exécutions d'agents"
        indexes = [
            models.Index(fields=["agent", "created_at"]),
            models.Index(fields=["provider", "model"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.agent.slug} | {self.provider}:{self.model} | {self.status}"

    def mark_finished(self) -> None:
        """
        Marque la fin du run, calcule la latence si besoin et applique la mise à jour budget.
        """
        if not self.finished_at:
            self.finished_at = timezone.now()
        if self.started_at and self.finished_at and not self.latency_ms:
            delta = self.finished_at - self.started_at
            self.latency_ms = int(delta.total_seconds() * 1000)

    def save(self, *args, **kwargs) -> None:
        """
        Sauvegarde en mettant à jour l'agrégat DailyBudget (si succès).
        """
        super().save(*args, **kwargs)
        # Si le run est terminé et réussi -> on agrège le coût de la journée
        if self.status == "success" and self.cost_eur and self.finished_at:
            DailyBudget.add_spend(self.agent, self.cost_eur, self.tokens_in, self.tokens_out)


class AgentToolCall(models.Model):
    """
    Trace un appel d'outil pendant un run.
    - name: nom de l'outil.
    - args/result: JSON minimal (attention à ne pas logguer de secrets).
    """

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    name = models.CharField(max_length=120)
    success = models.BooleanField(default=True)

    args = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Appel d'outil"
        verbose_name_plural = "Appels d'outils"
        indexes = [models.Index(fields=["name", "created_at"])]

    def __str__(self) -> str:
        return f"{self.name} ({'ok' if self.success else 'ko'})"


class DailyBudget(models.Model):
    """
    Agrégat budgétaire quotidien par agent.
    - Garantit (via add_spend) une observation simple du plafond journalier.
    """

    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="daily_budgets")
    date = models.DateField(default=local_today)
    spent_eur = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0.0000"))
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Budget quotidien agent"
        verbose_name_plural = "Budgets quotidiens agents"
        unique_together = [("agent", "date")]
        indexes = [models.Index(fields=["agent", "date"])]

    def __str__(self) -> str:
        return f"{self.agent.slug} @ {self.date} = {self.spent_eur}€"

    @classmethod
    def add_spend(
        cls,
        agent: AgentProfile,
        amount_eur: Decimal,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> "DailyBudget":
        """
        Incrémente l'agrégat quotidien pour un agent.
        ⚠️ À appeler uniquement après un run comptabilisé (status=success).
        """
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(
                agent=agent,
                date=local_today(),
                defaults=dict(spent_eur=Decimal("0.0000"), tokens_in=0, tokens_out=0),
            )
            obj.spent_eur = (obj.spent_eur or Decimal("0.0000")) + (amount_eur or Decimal("0.0000"))
            obj.tokens_in = (obj.tokens_in or 0) + int(tokens_in or 0)
            obj.tokens_out = (obj.tokens_out or 0) + int(tokens_out or 0)
            obj.save()
            return obj


# ──────────────────────────────────────────────────────────────────────────────
# Modèles pour admin/signaux existants
# ──────────────────────────────────────────────────────────────────────────────


class Manifesto(models.Model):
    version = models.CharField(max_length=50, unique=True)
    content = models.TextField()
    current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Manifeste global"
        verbose_name_plural = "Manifestes globaux"

    def __str__(self) -> str:
        return f"Manifeste v{self.version} ({'actif' if self.current else 'inactif'})"


class AgentSystemContext(models.Model):
    agent = models.OneToOneField(
        AgentProfile, on_delete=models.CASCADE, related_name="system_context"
    )
    context_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contexte système d’agent"
        verbose_name_plural = "Contextes système d’agent"

    def __str__(self) -> str:
        return f"CTX<{self.agent.slug}>"


class AgentMessageLog(models.Model):
    SCOPE_CHOICES = (
        ("private", "Privé"),
        ("personal", "Personnel"),
        ("shared", "Partagé"),
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    agent = models.ForeignKey(AgentProfile, null=True, blank=True, on_delete=models.SET_NULL)
    message = models.TextField()
    response = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default="private")
    tags = models.CharField(max_length=255, blank=True, default="")
    archived = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Log message agent"
        verbose_name_plural = "Logs messages agents"
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["agent", "scope"]),
        ]

    def __str__(self) -> str:
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {first_chars(self.message, 64)}"


class AgentImpactReport(models.Model):
    IMPACT_LEVELS = (
        ("none", "Aucun"),
        ("low", "Faible"),
        ("medium", "Moyen"),
        ("high", "Fort"),
        ("critical", "Bloquant"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    agent = models.ForeignKey(AgentProfile, null=True, blank=True, on_delete=models.SET_NULL)
    message = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")
    impact_level = models.CharField(max_length=20, choices=IMPACT_LEVELS, default="none")
    alert_jared = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Rapport d’impact agent"
        verbose_name_plural = "Rapports d’impact agents"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["impact_level"]),
        ]


class JaredLog(models.Model):
    """
    Journal stratégique (utilisé par l’admin).
    """

    STATUT_CHOICES = [
        ("todo", "À faire"),
        ("done", "Terminé"),
        ("waiting", "En attente"),
        ("alert", "Alerte"),
        ("note", "Note"),
        ("info", "Info"),
    ]
    PRIORITE_CHOICES = [
        ("low", "Faible"),
        ("medium", "Moyenne"),
        ("high", "Élevée"),
        ("critical", "Critique"),
    ]

    message = models.TextField()
    reponse = models.TextField(blank=True, default="")

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    agent_cible = models.ForeignKey(AgentProfile, null=True, blank=True, on_delete=models.SET_NULL)

    statut = models.CharField(max_length=16, choices=STATUT_CHOICES, default="todo")
    priorite = models.CharField(max_length=16, choices=PRIORITE_CHOICES, default="medium")

    deadline = models.DateTimeField(null=True, blank=True)
    suivi = models.BooleanField(default=False)
    confidentiel = models.BooleanField(default=False)

    tags = models.CharField(max_length=255, blank=True, default="")

    horodatage = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Journal stratégique (Jared)"
        verbose_name_plural = "Journaux stratégiques (Jared)"
        indexes = [
            models.Index(fields=["statut"]),
            models.Index(fields=["priorite"]),
            models.Index(fields=["horodatage"]),
        ]

    def __str__(self) -> str:
        return f"JaredLog<{first_chars(self.message, 48)}>"


# ──────────────────────────────────────────────────────────────────────────────
# Profil sécurité (auth préflight : teinte + ordre émojis + sandbox)
# ──────────────────────────────────────────────────────────────────────────────


class UserSecurityProfile(models.Model):
    """
    Stocke les secrets "préflight" d’un utilisateur (superuser de confiance).
    - secret_hue : teinte HSL attendue (0..359)
    - hue_tolerance : tolérance en degrés (+/-)
    - emoji_order_hash : HMAC-SHA256 sur la séquence d’indices "i0|i1|i2|i3" + nonce
    - emoji_nonce : protection pré-image
    - sandbox_until : si défini, la session doit rester en sandbox jusqu’à cette date
    - fail_count, last_fail_at : anti-bruteforce soft
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security_profile"
    )

    secret_hue = models.PositiveSmallIntegerField(default=202)  # 0..359
    hue_tolerance = models.PositiveSmallIntegerField(default=8)  # +/- 8°

    emoji_order_hash = models.CharField(max_length=128, blank=True, default="")
    emoji_nonce = models.CharField(max_length=32, blank=True, default="")

    fail_count = models.PositiveIntegerField(default=0)
    last_fail_at = models.DateTimeField(null=True, blank=True)
    sandbox_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Méthodes utilitaires ────────────────────────────────────────────────

    def set_emoji_secret(self, order: List[int]) -> None:
        """
        Définit la séquence secrète (exactement 4 indices).
        Stockage = HMAC_SHA256( "i0|i1|i2|i3|nonce", SECRET_KEY )
        """
        if not isinstance(order, list) or len(order) != 4:
            raise ValueError("La séquence doit contenir exactement 4 indices.")
        nonce = secrets.token_hex(8)
        payload = f"{order[0]}|{order[1]}|{order[2]}|{order[3]}|{nonce}"
        key = settings.SECRET_KEY.encode("utf-8")
        digest = hmac.new(key, payload.encode("utf-8"), sha256).hexdigest()
        self.emoji_nonce = nonce
        self.emoji_order_hash = digest

    def verify_emoji_order(self, order: List[int]) -> bool:
        """
        Vérifie la séquence fournie (exactement 4 entiers).
        """
        if not self.emoji_nonce or not self.emoji_order_hash:
            return False
        try:
            i0, i1, i2, i3 = order
        except Exception:
            return False
        payload = f"{i0}|{i1}|{i2}|{i3}|{self.emoji_nonce}"
        key = settings.SECRET_KEY.encode("utf-8")
        digest = hmac.new(key, payload.encode("utf-8"), sha256).hexdigest()
        return hmac.compare_digest(digest, self.emoji_order_hash)

    def verify_hue(self, hue: int) -> bool:
        """
        Vérifie la teinte (0..359) avec tolérance +/- sur un cercle (360°).
        """
        try:
            h = int(hue)
        except Exception:
            return False
        h = max(0, min(359, h))
        # Distance circulaire
        diff = min((h - self.secret_hue) % 360, (self.secret_hue - h) % 360)
        return diff <= int(self.hue_tolerance)

    def mark_failure(self) -> None:
        """
        En cas d’échec : incrémente le compteur et place éventuellement en sandbox temporaire.
        """
        self.fail_count = (self.fail_count or 0) + 1
        self.last_fail_at = timezone.now()
        if self.fail_count >= 5:
            self.sandbox_until = timezone.now() + timedelta(minutes=30)

    def clear_failures(self) -> None:
        """Réinitialise les échecs et l’horodatage associé."""
        self.fail_count = 0
        self.last_fail_at = None

    def __str__(self) -> str:
        return f"UserSecurityProfile<{self.user.username}>"


# ──────────────────────────────────────────────────────────────────────────────
# Hooks & bonnes pratiques
# ──────────────────────────────────────────────────────────────────────────────


def preflight_budget_check(agent: AgentProfile, estimated_cost_eur: Decimal) -> None:
    """
    Contrôle pré-exécution : l'agent a-t-il assez de budget pour lancer un run ?
    - Laisse passer si hard_stop_on_exceed=False.
    - Lève ValidationError sinon.
    """
    if not agent.can_spend(estimated_cost_eur):
        rest = agent.remaining_today()
        raise ValidationError(
            f"Budget insuffisant pour {agent.slug} : restant={rest:.4f}€, requis={estimated_cost_eur:.4f}€."
        )
