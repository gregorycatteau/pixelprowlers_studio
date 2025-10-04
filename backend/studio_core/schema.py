# studio_core/schema.py
# -----------------------------------------------------------------------------
# Schéma GraphQL Strawberry pour PixelProwlers Studio.
# - Query.ping  : smoke test ("pong")
# - Query.me    : renvoie le username si authentifié
# - Mutation.echo : test mutation (boucle)
# - Mutation.analyze_schema : action sensible protégée par le scope "agents:analyze_schema"
# -----------------------------------------------------------------------------
from __future__ import annotations

from typing import Optional

import strawberry
from strawberry.types import Info

# Permissions basées sur des "scopes" (JWT/AgentProfile)
from .permissions import scope_perm


@strawberry.type
class Query:
    """Entrée de requêtes GraphQL."""

    @strawberry.field
    def ping(self) -> str:
        """
        Smoke test GraphQL.
        Retour :
            - "pong" si le service est OK.
        """
        return "pong"

    @strawberry.field
    def me(self, info: Info) -> Optional[str]:
        """
        Renvoie le username si l'utilisateur est authentifié, sinon None.
        Args:
            info: contexte Strawberry (accès à request/user).
        """
        user = info.context.request.user
        return None if user.is_anonymous else user.username


@strawberry.type
class Mutation:
    """Entrée des mutations GraphQL."""

    @strawberry.mutation
    def echo(self, message: str) -> str:
        """
        Renvoie le message (test mutation).
        Args:
            message: texte à renvoyer tel quel.
        """
        return message

    @strawberry.mutation(permission_classes=[scope_perm("agents:analyze_schema")])
    def analyze_schema(self, info: Info, schema_dump: str) -> str:
        """
        Analyse ultra-simple d'un dump SQL (ex: DDL PostgreSQL) — démonstration.
        ⚠️ Mutation protégée par le scope "agents:analyze_schema".

        Args:
            info: contexte Strawberry (accès à request/auth).
            schema_dump: contenu texte du DDL à analyser.

        Retour:
            Résumé texte (nb de tables détectées, présence d'index, etc.)
            -> but pédagogique; à spécialiser ensuite (normalisation, index, partitionnement).
        """
        # --- mini "analyse" purement indicative (pas de parsing complet) ---
        lines = [ln.strip().strip(";") for ln in schema_dump.splitlines() if ln.strip()]
        nb_tables = sum(1 for ln in lines if ln.upper().startswith("CREATE TABLE"))
        nb_indexes = sum(1 for ln in lines if ln.upper().startswith("CREATE INDEX"))
        has_fk = any(" FOREIGN KEY " in ln.upper() for ln in lines)
        has_unique = any(" UNIQUE " in ln.upper() for ln in lines)

        summary = [
            f"Tables détectées : {nb_tables}",
            f"Index détectés  : {nb_indexes}",
            f"Contraintes FK  : {'oui' if has_fk else 'non'}",
            f"Contraintes UNIQUE : {'oui' if has_unique else 'non'}",
        ]
        # Idées d’amélioration futures : vérif PK, normalisation (1NF/2NF/3NF), clés candidates, index composite, etc.
        return "\n".join(summary)


# Schéma principal
schema = strawberry.Schema(query=Query, mutation=Mutation)
