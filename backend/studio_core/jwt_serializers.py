# studio_core/jwt_serializers.py
# -----------------------------------------------------------------------------
# Sérialiseur JWT : ajoute des claims utiles:
# - username
# - agent (True si AgentProfile actif)
# - scopes (scopes de l'agent + scopes owners si l'utilisateur est owner)
# Les scopes "owners" proviennent de la variable d'env OWNERS_SCOPES (ex: "root:*,agents:*").
# Groupe owners configurable via OWNERS_GROUP_NAME (défaut: "owners").
# -----------------------------------------------------------------------------
from __future__ import annotations

import os
from typing import List

from django.contrib.auth.models import Group
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


def _parse_scopes_env(value: str | None) -> List[str]:
    """
    Parse une chaîne "a,b,c" en liste de scopes.
    Retourne [] si value est vide/None.
    """
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _owners_group_name() -> str:
    """
    Nom du groupe 'owners' (surchargable via l'env OWNERS_GROUP_NAME).
    """
    return os.getenv("OWNERS_GROUP_NAME", "owners")


def _owners_scopes() -> List[str]:
    """
    Scopes à ajouter aux owners (liste CSV dans OWNERS_SCOPES).
    Exemple: OWNERS_SCOPES="root:*,agents:*,db:*"
    """
    return _parse_scopes_env(os.getenv("OWNERS_SCOPES"))


class AgentTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Sérialiseur JWT qui enrichit le token avec des claims utiles:
    - username (pour logging côté client/outillage)
    - agent: bool (AgentProfile actif)
    - scopes: liste de scopes (AgentProfile.scopes + OWNERS_SCOPES si owner)
    """

    @classmethod
    def get_token(cls, user):
        """
        Construit le JWT en y injectant les claims décrits.
        """
        token = super().get_token(user)
        token["username"] = user.username

        # 1) Déterminer si user est un "agent" (au sens AgentProfile actif)
        token["agent"] = False
        token["scopes"] = []

        try:
            from accounts.models import AgentProfile  # import tardif pour éviter cycles

            ap = AgentProfile.objects.filter(user=user, is_active=True).first()
            if ap:
                token["agent"] = True
                token["scopes"] = list(ap.scopes or [])
        except Exception:
            # Pas de modèle, pas de scopes d'agent
            token["agent"] = False
            token["scopes"] = []

        # 2) Owners ? Si oui, ajouter les scopes "owners"
        try:
            owners_group = Group.objects.filter(name=_owners_group_name()).first()
            if owners_group and user.is_active and user.groups.filter(id=owners_group.id).exists():
                token["owner"] = True
                token["scopes"] = list(set(token["scopes"] + _owners_scopes()))
            else:
                token["owner"] = False
        except Exception:
            token["owner"] = False

        return token
