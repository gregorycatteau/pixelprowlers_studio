# studio_core/graphql_rules.py
# -------------------------------------------------------------------
# Règle de profondeur max pour limiter la complexité des requêtes GQL.
# -------------------------------------------------------------------
from __future__ import annotations

from graphql import GraphQLError, ValidationRule


class MaxDepthRule(ValidationRule):
    """Limite la profondeur d'une requête GraphQL (défense anti DoS logique)."""

    def __init__(self, context, max_depth: int = 8):
        super().__init__(context)
        self.max_depth = max_depth
        self.depth = 0
        self.max_seen = 0

    def enter(self, node, *_):
        kind = getattr(node, "kind", "")
        if kind in ("field", "inline_fragment", "fragment_definition"):
            self.depth += 1
            self.max_seen = max(self.max_seen, self.depth)
            if self.max_seen > self.max_depth:
                self.context.report_error(
                    GraphQLError(f"Query depth {self.max_seen} exceeds max {self.max_depth}")
                )

    def leave(self, node, *_):
        kind = getattr(node, "kind", "")
        if kind in ("field", "inline_fragment", "fragment_definition"):
            self.depth -= 1


def make_max_depth_rule(max_depth: int):
    """Factory d'une règle paramétrée."""

    class _Rule(MaxDepthRule):
        def __init__(self, context):
            super().__init__(context, max_depth=max_depth)

    return _Rule
