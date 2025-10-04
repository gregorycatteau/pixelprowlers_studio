from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

User = get_user_model()


class AgentProfile(models.Model):
    """
    Profil d'agent IA adossé à un compte utilisateur (compte de service).

    Sécurité:
    - Les agents sont des comptes de service dédiés aux appels API.
    - Par défaut, nous les mettons 'is_staff=True' pour pouvoir leur appliquer
      des permissions DRF spécifiques (et potentiellement des vues admin API),
      tout en BLOQUANT l'accès à l'interface d'admin Django via un AdminSite custom.
    - Les actions fines sont contrôlées par des 'scopes' signés dans le JWT.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="agent_profile")
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="created_agents"
    )
    label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    scopes = ArrayField(
        base_field=models.CharField(max_length=64),
        default=list,
        blank=True,
        help_text="Liste de scopes fonctionnels accordés à l'agent (ex: 'articles:read').",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agent IA"
        verbose_name_plural = "Agents IA"

    def __str__(self) -> str:
        """Représentation lisible de l'agent."""
        return f"Agent({self.user.username})"


class AuditLog(models.Model):
    """
    Journal d'audit minimaliste pour tracer les appels API.

    Champs enregistrés:
    - created_at : horodatage (indexé)
    - user, username, is_agent : qui fait l'appel ?
    - method, path, status_code : quoi / où
    - jwt_jti, jwt_scopes : traçage du token et des capacités utilisées
    - ip, user_agent : d'où provient l'appel
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    username = models.CharField(max_length=150, blank=True, default="")
    is_agent = models.BooleanField(default=False)

    method = models.CharField(max_length=8)
    path = models.TextField()
    status_code = models.IntegerField()

    jwt_jti = models.CharField(max_length=64, blank=True, default="")
    jwt_scopes = ArrayField(
        base_field=models.CharField(max_length=64),
        default=list,
        blank=True,
        help_text="Scopes vus dans le JWT au moment de l'appel.",
    )

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"[{self.created_at.isoformat()}] {self.method} {self.path} {self.status_code} ({self.username})"
