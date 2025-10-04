# -*- coding: utf-8 -*-
"""
Vue GraphQL sécurisée (fonctionnelle) pour PixelProwlers Studio.

✅ Exige un operationName (configurable)
✅ Limite la profondeur des requêtes (garde-fou anti-abus)
   - Mode "naïf" (comptage d'accolades)
   - Mode "AST" (précis : fragments, inline fragments)
✅ Rate-limit côté app si django-ratelimit est installé
✅ Journalise les refus (raison, IP, UA)

Sécurité > Ergonomie > Design — priorité à l’anti-abus.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

# GraphQL (Strawberry)
from strawberry.django.views import GraphQLView  # type: ignore

from .schema import schema  # Ton schéma existant

# Rate-limit optionnel
try:
    from ratelimit.decorators import ratelimit  # type: ignore

    _HAS_RATELIMIT = True
except Exception:
    _HAS_RATELIMIT = False

# AST depth (si graphql-core installé)
try:
    from graphql import (  # type: ignore
        DocumentNode,
        FieldNode,
        FragmentDefinitionNode,
        InlineFragmentNode,
        OperationDefinitionNode,
        parse,
    )

    _HAS_GRAPHQL_CORE = True
except Exception:
    _HAS_GRAPHQL_CORE = False

logger = logging.getLogger("graphql.security")


# ──────────────────────────────────────────────────────────────────────────────
# Paramètres (overridables via settings)
# ──────────────────────────────────────────────────────────────────────────────
REQUIRE_OPERATION_NAME: bool = getattr(
    settings, "GRAPHQL_REQUIRE_OPERATION_NAME", not settings.DEBUG
)
MAX_DEPTH: int = int(getattr(settings, "GRAPHQL_MAX_DEPTH", 8))
RATE_SPEC: str = getattr(settings, "GRAPHQL_RATE", "")  # ex: "60/m" si activé
DEPTH_MODE: str = getattr(settings, "GRAPHQL_DEPTH_MODE", "naive").lower()
# valeurs supportées: "naive", "ast" (si graphql-core dispo)


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────────────────────────
def _client_ip(request: HttpRequest) -> str:
    """Retourne l'adresse IP client (XFF > REMOTE_ADDR)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "-")


def _parse_body(request: HttpRequest) -> Dict[str, Any]:
    """Parse le body GraphQL en JSON (ou form-encoded minimal)."""
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads((request.body or b"{}").decode())
        except Exception:
            return {}
    # Fallback très simple
    return {
        "query": request.POST.get("query", ""),
        "operationName": request.POST.get("operationName") or None,
        "variables": json.loads(request.POST.get("variables") or "{}"),
    }


# ── Profondeur : mode naïf (comptage d'accolades) ─────────────────────────────
def _compute_depth_naive(query: str) -> int:
    depth = 0
    max_seen = 0
    for ch in query:
        if ch == "{":
            depth += 1
            if depth > max_seen:
                max_seen = depth
        elif ch == "}":
            depth -= 1
    return max_seen


# ── Profondeur : mode AST (précis, gère fragments) ───────────────────────────
def _compute_depth_ast(query: str) -> int:
    """
    Calcule la profondeur maximale via l'AST GraphQL.
    - Gère Field, InlineFragment, FragmentSpread
    - Retourne 0 si parsing impossible ou si graphql-core absent
    """
    if not _HAS_GRAPHQL_CORE:
        return 0
    try:
        doc: DocumentNode = parse(query)
    except Exception:
        return 0

    fragments: Dict[str, FragmentDefinitionNode] = {}
    operations: List[OperationDefinitionNode] = []

    for d in doc.definitions:
        if isinstance(d, FragmentDefinitionNode):
            fragments[d.name.value] = d
        elif isinstance(d, OperationDefinitionNode):
            operations.append(d)

    def sel_depth(selection_set, seen_fragments: Optional[Dict[str, bool]] = None) -> int:
        if not selection_set:
            return 0
        seen_fragments = seen_fragments or {}
        max_child = 0
        for sel in selection_set.selections:
            # Field
            if isinstance(sel, FieldNode):
                d = 1 + sel_depth(sel.selection_set, seen_fragments)
                if d > max_child:
                    max_child = d
            # InlineFragment
            elif isinstance(sel, InlineFragmentNode):
                d = 1 + sel_depth(sel.selection_set, seen_fragments)
                if d > max_child:
                    max_child = d
            # FragmentSpread
            else:
                # fragment spread -> retrouver le fragment et éviter cycles
                frag_name = getattr(sel.name, "value", "")
                if frag_name and frag_name in fragments and not seen_fragments.get(frag_name):
                    seen_fragments[frag_name] = True
                    frag = fragments[frag_name]
                    d = 1 + sel_depth(frag.selection_set, seen_fragments)
                    if d > max_child:
                        max_child = d
                    seen_fragments.pop(frag_name, None)
        return max_child

    max_depth = 0
    for op in operations:
        d = sel_depth(op.selection_set)
        if d > max_depth:
            max_depth = d
    return max_depth


def _too_deep(query: str, max_depth: int) -> bool:
    """
    Renvoie True si la profondeur dépasse ou atteint le plafond autorisé.
    - 'naive' : plus rapide, approximatif
    - 'ast'   : plus précis, nécessite graphql-core
    """
    if not query.strip():
        return False
    if DEPTH_MODE == "ast" and _HAS_GRAPHQL_CORE:
        depth = _compute_depth_ast(query)
    else:
        depth = _compute_depth_naive(query)
    # 🔒 Plafond inclusif : on bloque si profondeur >= MAX_DEPTH
    return depth >= max_depth


# ──────────────────────────────────────────────────────────────────────────────
# Rate-limit décorateur
# ──────────────────────────────────────────────────────────────────────────────
def _rate_decorator(view_func):
    """Applique un rate-limit par IP si configuré et dispo."""
    if _HAS_RATELIMIT and RATE_SPEC:
        return ratelimit(key="ip", rate=RATE_SPEC, block=True)(view_func)
    return view_func


# ──────────────────────────────────────────────────────────────────────────────
# Vue sécurisée
# ──────────────────────────────────────────────────────────────────────────────
@csrf_exempt
@_rate_decorator
def secure_graphql_view(request: HttpRequest, *args, **kwargs):
    """
    Enveloppe sécurisée autour de la vue GraphQL Strawberry.

    - Valide l'operationName et la profondeur avant d'invoquer le resolver.
    - Loggue les refus avec IP/UA pour audit & corrélation.
    """
    if request.method == "POST":
        payload = _parse_body(request)
        query = (payload.get("query") or "").strip()
        operation_name = payload.get("operationName")

        # operationName exigée ?
        if REQUIRE_OPERATION_NAME and not operation_name:
            ip, ua = _client_ip(request), request.META.get("HTTP_USER_AGENT", "-")
            logger.warning(
                "Refus GraphQL: operationName manquant",
                extra={"ip": ip, "ua": ua, "path": request.path},
            )
            return JsonResponse(
                {"error": "operationName manquant (GRAPHQL_REQUIRE_OPERATION_NAME=1)"},
                status=400,
            )

        # profondeur max ?
        if query and _too_deep(query, MAX_DEPTH):
            ip, ua = _client_ip(request), request.META.get("HTTP_USER_AGENT", "-")
            logger.warning(
                "Refus GraphQL: profondeur excessive",
                extra={
                    "ip": ip,
                    "ua": ua,
                    "path": request.path,
                    "max_depth": MAX_DEPTH,
                    "mode": DEPTH_MODE,
                },
            )
            return JsonResponse(
                {"error": f"Profondeur de requête trop élevée (≥ {MAX_DEPTH})"},
                status=400,
            )

    # Si tout est OK, on délègue à Strawberry
    return GraphQLView.as_view(schema=schema)(request, *args, **kwargs)
