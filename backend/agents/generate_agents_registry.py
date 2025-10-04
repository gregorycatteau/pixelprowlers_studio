# pixelprowlers-backend/agents/generate_agents_registry.py

import json
import os
from pathlib import Path

from dotenv import load_dotenv

AGENTS_DIR = Path(__file__).resolve().parent
ENV_PATH = AGENTS_DIR / ".env"
REGISTRY_PATH = AGENTS_DIR / "agents_registry.json"

# Chargement des variables d’environnement
load_dotenv(dotenv_path=ENV_PATH)


def load_env_ids():
    """Charge les IDs depuis le .env"""
    ids = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and line.strip().endswith("_ASSISTANT_ID"):
                    key, val = line.strip().split("=", 1)
                    name = key.replace("_ASSISTANT_ID", "").capitalize()
                    ids[name] = val
    return ids


def collect_agent_profiles():
    """Fusionne tous les profils JSON et ajoute l'ID si dispo"""
    profiles = {}
    env_ids = load_env_ids()

    for file in AGENTS_DIR.glob("*.json"):
        if file.name == "agents_registry.json":
            continue

        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            name = data.get("name", file.stem).capitalize()
            data["assistant_id"] = env_ids.get(name, "❓ Not yet registered")
            profiles[name] = data
        except Exception as e:
            print(f"⚠️ Erreur lors du traitement de {file.name} : {e}")

    return profiles


def write_registry(profiles):
    """Écrit le fichier agents_registry.json enrichi"""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Fichier agents_registry.json généré avec {len(profiles)} agents.")


def main():
    print("🔄 Génération automatique de agents_registry.json...")
    profiles = collect_agent_profiles()
    write_registry(profiles)


if __name__ == "__main__":
    main()
