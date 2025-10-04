import json
import logging
import os

from ai_assistants.models import AgentProfile
from django.conf import settings
from dotenv import load_dotenv

# === Logger ===
logger = logging.getLogger(__name__)

# === Chargement des variables d’environnement depuis agents/.env ===
AGENTS_DIR = os.path.join(settings.BASE_DIR, "agents")
load_dotenv(dotenv_path=os.path.join(AGENTS_DIR, ".env"))


def import_agents():
    print("")
    print("=== 🚀 Import des agents IA depuis le dossier `agents/` ===")
    print("")

    if not os.path.exists(AGENTS_DIR):
        print(f"❌ Dossier introuvable : {AGENTS_DIR}")
        return

    created = 0
    updated = 0
    skipped = 0
    for filename in os.listdir(AGENTS_DIR):
        if not filename.endswith("_agent.json"):
            continue
        filepath = os.path.join(AGENTS_DIR, filename)
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Erreur de lecture JSON dans {filename} : {e}")
            continue

        # Récupère l’ID de l’assistant depuis .env
        key = f"{data['name'].upper()}_ID"
        assistant_id = os.getenv(key)
        if not assistant_id:
            print(f"⚠️ Aucun assistant_id trouvé pour {data['name']} dans .env (clé {key})")
            continue

        try:
            agent, created_flag = AgentProfile.objects.update_or_create(
                name=data["name"],
                defaults={
                    "assistant_id": assistant_id,
                    "description": data.get("description", ""),
                    "instructions": data.get("instructions", ""),
                    "model": data.get("model", "gpt-4o"),
                    "metadata": {
                        k: v
                        for k, v in data.items()
                        if k not in ["name", "description", "instructions", "model"]
                    },
                    "is_active": True,
                },
            )
            if created_flag:
                print(f"➕ Agent {agent.name} créé")
                created += 1
            else:
                print(f"🔁 Agent {agent.name} mis à jour")
                updated += 1
        except Exception as e:
            print(f"❌ Erreur avec {filename} : {e}")
            continue

    print("")
    print("📦 Import terminé.")
    print(f"  ➕ {created} créés")
    print(f"  🔁 {updated} mis à jour")
    print(f"  ✅ {skipped} ignorés (non valides)")
    print("")
