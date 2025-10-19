# -*- coding: utf-8 -*-
"""
Tests S7 ciblés sur les scripts d'observabilité/résilience pour répondre au filtre:
  pytest -q -k "monitor or resilience"

- Vérifie que les scripts existent
- Vérifie la validité de syntaxe Bash (bash -n)

Ces tests sont légers et ne lancent pas les scénarios (non-bloquants).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    # .../backend/studio_core/tests/test_*.py → remonter à la racine du repo
    return Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "relpath, keyword",
    [
        ("tools/test_resilience.sh", "resilience"),
        ("tools/monitor_eotp.sh", "monitor"),
    ],
)
def test_script_exists_and_bash_syntax_ok(relpath: str, keyword: str) -> None:
    root = _repo_root()
    script_path = root / relpath

    assert script_path.exists(), f"{relpath} doit exister (keyword={keyword})"
    assert script_path.is_file(), f"{relpath} doit être un fichier (keyword={keyword})"

    # Validation de syntaxe bash (sans exécuter le script)
    # bash -n: lit le script et retourne 0 si la syntaxe est OK.
    try:
        completed = subprocess.run(
            ["bash", "-n", str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("bash introuvable sur ce système de test")

    assert (
        completed.returncode == 0
    ), f"Syntaxe Bash invalide pour {relpath} (keyword={keyword}). stderr:\n{completed.stderr}"
