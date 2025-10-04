# backend/ai_assistants/file_reader.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

"""
Lecteur sécurisé de fichiers frontend (Nuxt 4) pour inspection par les agents.
- Base front attendue : <repo>/frontend/app
- Fichiers autorisés : .vue (components/pages/layouts), .css (assets/css) — read-only
- Protection : pas de chemins absolus, pas de '..', whitelist de caractères, confinement dans la base.

Configuration :
- FRONTEND_APP_PATH (ENV, ABSOLU recommandé) ex: /abs/path/pixelprowlers_studio/frontend/app
- Fallbacks automatiques :
    - <repo>/frontend/app
    - <repo_parent>/pixelprowlers-frontend/app
"""

# --------- Résolution de la base Nuxt "app" ---------

_ALLOWED_CHARS_RE = re.compile(r"^[A-Za-z0-9_\-\/\.]+$")

# Sous-répertoires racines autorisés (à l'intérieur de "app")
_ALLOWED_ROOTS = {
    "components",  # .vue
    "pages",  # .vue
    "layouts",  # .vue
    "assets/css",  # .css (pour tailwind: app/assets/css/main.css)
}

# Extensions autorisées
_ALLOWED_EXTS = {".vue", ".css"}


def _guess_app_dir() -> Optional[Path]:
    """
    Guesses classiques :
      - <repo>/frontend/app
      - <repo_parent>/pixelprowlers-frontend/app
    """
    # .../backend/ai_assistants/file_reader.py -> parents[2] == <repo>
    repo_root = Path(__file__).resolve().parents[2]
    guesses = [
        repo_root / "frontend" / "app",
        repo_root.parent / "pixelprowlers-frontend" / "app",
    ]
    for g in guesses:
        g = g.resolve()
        if g.exists() and g.is_dir():
            return g
    return None


def _resolve_app_base() -> Optional[Path]:
    env = os.getenv("FRONTEND_APP_PATH", "").strip()
    if env:
        try:
            p = Path(env).resolve()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    return _guess_app_dir()


FRONTEND_APP_PATH: Optional[Path] = _resolve_app_base()


# --------- Sécurité & lecture ---------


def _is_allowed_relative_path(rel: str) -> bool:
    """
    Valide un chemin relatif :
      - caractères whitelist
      - pas de chemin absolu
      - pas de '..'
      - commence par un des _ALLOWED_ROOTS
      - extension autorisée
    """
    if not rel or rel.startswith("/"):
        return False
    if ".." in rel:
        return False
    if not _ALLOWED_CHARS_RE.match(rel):
        return False

    # root autorisé ?
    if not any(rel.startswith(root + "/") or rel == root for root in _ALLOWED_ROOTS):
        return False

    # extension autorisée ?
    ext = Path(rel).suffix.lower()
    return ext in _ALLOWED_EXTS


def _safe_join(base: Path, relative: str) -> Optional[Path]:
    if not _is_allowed_relative_path(relative):
        return None
    try:
        p = (base / relative).resolve()
        p.relative_to(base)  # confinement dans la base
    except Exception:
        return None
    return p


def read_front_file(relative_path: str) -> str:
    """
    Lit un fichier frontend autorisé à partir de la base Nuxt 'app'.
    Exemples valides :
      - 'components/MyCard.vue'
      - 'pages/index.vue'
      - 'layouts/default.vue'
      - 'assets/css/main.css'
    Retourne le contenu ou un message d'erreur explicite.
    """
    base = FRONTEND_APP_PATH
    if base is None:
        return (
            "❌ FRONTEND_APP_PATH introuvable.\n"
            "   -> Exporte une variable d'environnement ABSOLUE, ex:\n"
            '      export FRONTEND_APP_PATH="/abs/path/to/pixelprowlers_studio/frontend/app"\n'
            "   Ou place ton front dans ./frontend/app (à la racine du repo)."
        )

    path = _safe_join(base, (relative_path or "").strip())
    if not path:
        return (
            "❌ Chemin invalide (sécurité : chemin relatif, racine autorisée, extension .vue/.css)."
        )

    if not path.exists():
        return f"❌ Le fichier '{relative_path}' est introuvable dans {base}."

    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ Erreur lors de la lecture : {type(e).__name__}: {e}"


# ⚠️ Compatibilité ascendante avec l’ancien nom
def read_vue_file(filename: str) -> str:
    """
    Alias rétrocompatible : lit un composant .vue depuis app/components|pages|layouts.
    """
    if not filename.endswith(".vue"):
        return (
            "❌ Utilise read_front_file() pour les extensions non .vue (ex: assets/css/main.css)."
        )
    # Si aucun dossier donné, on suppose "components/"
    rel = filename if ("/" in filename) else f"components/{filename}"
    return read_front_file(rel)
