# pixelprowlers-backend/agents/register_agents.py

import json
import os
from pathlib import Path

try:
    import openai
except ModuleNotFoundError:
    openai = None
from dotenv import load_dotenv

# === INIT ENVIRONNEMENT ===
AGENTS_DIR = Path(__file__).resolve().parent
ENV_PATH = AGENTS_DIR / ".env"
REGISTRY_PATH = AGENTS_DIR / "agents_registry.json"

# Chargement des variables d'environnement
load_dotenv(dotenv_path=ENV_PATH)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def ensure_openai_ready():
    """Initialise le client OpenAI uniquement pour les agents à inscrire."""
    if openai is None:
        raise ModuleNotFoundError(
            "❌ Package openai absent. Installe-le (ex: poetry add openai) pour enregistrer de nouveaux agents."
        )
    if not getattr(openai, "api_key", None):
        if not OPENAI_API_KEY:
            raise ValueError(
                "❌ Clé API OpenAI manquante (définis OPENAI_API_KEY dans ton environnement)."
            )
        openai.api_key = OPENAI_API_KEY
    return openai


# === UTILS ===


def load_existing_env_ids():
    """Retourne {ENV_KEY: ID} pour chaque clé *_ASSISTANT_ID dans .env."""
    existing = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k.endswith("_ASSISTANT_ID"):
                        existing[k] = v
    return existing


def truncate_field(value: str, max_len: int) -> str:
    """
    Tronque une chaîne si elle dépasse max_len.
    Ajoute "..." en fin pour indiquer la coupe.
    """
    if not isinstance(value, str):
        return value
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def register_agent_from_file(json_path: Path, existing_ids: dict):
    """
    Enregistre l'agent si non déjà présent.
    Filtre + tronque les champs non supportés.
    Retourne {name: assistant_id} ou {}.
    """
    full_data = json.loads(json_path.read_text(encoding="utf-8"))
    name = full_data.get("name", "unknown")
    env_key = f"{name.upper()}_ASSISTANT_ID"

    # Skip si déjà en .env
    if env_key in existing_ids:
        print(f"⏭️ Agent {name} déjà enregistré (ID : {existing_ids[env_key]})")
        return {name: existing_ids[env_key]}

    print(f"\n📤 Enregistrement de l'agent : {name}...")
    client = ensure_openai_ready()

    # Champs autorisés pour l'API
    allowed = {"name", "description", "instructions", "model", "tools"}
    data_api = {k: v for k, v in full_data.items() if k in allowed}

    # Tronquage selon contrainte API
    if "description" in data_api:
        data_api["description"] = truncate_field(data_api["description"], max_len=512)
    if "instructions" in data_api:
        data_api["instructions"] = truncate_field(data_api["instructions"], max_len=1024)

    try:
        resp = client.beta.assistants.create(**data_api)
        aid = resp.id

        # Ajouter dans .env
        with open(ENV_PATH, "a", encoding="utf-8") as envf:
            envf.write(f"{env_key}={aid}\n")

        print(f"✅ Agent {name} enregistré avec ID : {aid}")
        return {name: aid}

    except Exception as e:
        print(f"❌ Erreur lors de l'enregistrement de {name} : {e}")
        return {}


def save_registry(agent_dict: dict):
    """Écrit le JSON final des agents dans agents_registry.json."""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(agent_dict, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Mise à jour de agents_registry.json ({len(agent_dict)} agents).")


def main():
    print("🚀 Démarrage de l’enregistrement des agents IA…")
    existing = load_existing_env_ids()
    registered = {}

    for file in AGENTS_DIR.glob("*.json"):
        if file.name == "agents_registry.json":
            continue
        result = register_agent_from_file(file, existing)
        registered.update(result)

    print("\n📝 Résumé des agents enregistrés :")
    for nm, aid in registered.items():
        print(f"🔹 {nm} → {aid}")

    save_registry(registered)


if __name__ == "__main__":
    main()
