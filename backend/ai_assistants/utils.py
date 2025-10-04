# backend/ai_assistants/utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from .utils.agent_schema import validate_agent_profile

"""
Découverte/chargement des profils d'agents (schéma v2.1).
Ton layout réel : pixelprowlers_studio/backend/agents/*.json

- Accepte "claire.json" et "claire_agent.json"
- Dérive le slug depuis manifest.identity.slug sinon depuis le nom de fichier
- Valide au schéma v2.1, remonte les erreurs par fichier
"""

# __file__ = backend/ai_assistants/utils.py
# parents[0] = backend/ai_assistants
# parents[1] = backend
AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9\-]+")


def _slugify(name: str) -> str:
    s = name.lower().strip().replace("_", "-").replace(" ", "-")
    s = _SLUG_CLEAN_RE.sub("-", s).strip("-")
    return s or "agent"


def _slug_from_filename(stem: str) -> str:
    # "claire_agent" -> "claire" ; "jared" -> "jared"
    return stem[:-7] if stem.endswith("_agent") and len(stem) > 7 else stem


def list_profile_files() -> List[Path]:
    """Retourne tous les fichiers .json dans backend/agents."""
    if not AGENTS_DIR.exists():
        return []
    return sorted(AGENTS_DIR.glob("*.json"))


def load_profile_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_registered_agents() -> Dict[str, Dict[str, Any]]:
    """
    Scanne backend/agents et retourne:
    {
      "<slug>": {
        "name": str,
        "path": str,
        "profile_version": str,
        "schema_version": str,
        "errors": [str, ...]
      },
      ...
    }
    Note: les JSON non migrés en v2.1 remonteront des erreurs — attendu.
    """
    results: Dict[str, Dict[str, Any]] = {}
    for fp in list_profile_files():
        try:
            data = load_profile_file(fp)
            errors = validate_agent_profile(data)
            ident = data.get("identity", {})
            slug = ident.get("slug") or _slug_from_filename(fp.stem)
            slug = _slugify(slug)
            results[slug] = {
                "name": ident.get("name", slug),
                "path": str(fp),
                "profile_version": data.get("profile_version", ""),
                "schema_version": data.get("schema_version", ""),
                "errors": errors,
            }
        except Exception as e:
            stem_slug = _slugify(_slug_from_filename(fp.stem))
            results[stem_slug] = {
                "name": stem_slug,
                "path": str(fp),
                "profile_version": "",
                "schema_version": "",
                "errors": [f"Load error: {type(e).__name__}: {e}"],
            }
    return results


def load_manifest_by_slug(slug: str) -> Dict[str, Any]:
    """
    Charge le manifeste d'un agent par slug.
    Cherche d'abord <slug>.json puis <slug>_agent.json dans backend/agents/.
    Valide le schéma v2.1 (ValueError si invalide).
    """
    candidates = [
        AGENTS_DIR / f"{slug}.json",
        AGENTS_DIR / f"{slug}_agent.json",
    ]
    for path in candidates:
        if path.exists():
            data = load_profile_file(path)
            errors = validate_agent_profile(data)
            if errors:
                raise ValueError(f"Profil '{slug}' invalide: {errors}")
            return data
    raise FileNotFoundError(
        f"Profil '{slug}' introuvable dans {AGENTS_DIR} "
        f"(attendus: {', '.join(p.name for p in candidates)})"
    )
