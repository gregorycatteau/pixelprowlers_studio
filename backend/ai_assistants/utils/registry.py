"""Helpers for interacting with the local agents registry file."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"
REGISTRY_PATH = AGENTS_DIR / "agents_registry.json"


@lru_cache(maxsize=1)
def load_agents_registry() -> Dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def get_assistant_id_from_registry(agent_name: str) -> str | None:
    registry = load_agents_registry()
    # Registry is stored with capitalised keys (e.g. "Bruce")
    return registry.get(agent_name) or registry.get(agent_name.capitalize())
