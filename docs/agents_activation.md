Partager

Créer une demande d’extraction


Tu as carte blanche pour explorer tous les fichiers du repo. Ta mission du jour est de déterminer, en l'état actuel des choses la meilleure manière d'activer les agents ia qui ont été jusqu'ici définis.
Copier
Summary

Ajout d’un guide décrivant étape par étape comment préparer l’environnement, enregistrer les assistants OpenAI, importer les profils dans Django et valider leur activation applicative.

Testing

⚠️ Aucun test exécuté (modification de documentation uniquement)


Fichier (1)

docs/agents_activation.md
Nouveau



Diff
Journaux

docs/agents_activation.md
Nouveau
+60
-0

# Activation des agents IA PixelProwlers

Ce guide synthétise la meilleure façon d'activer les agents IA déjà définis dans le dépôt. Il couvre la préparation de l'environnement, l'enregistrement côté OpenAI, l'import dans Django et la vérification de l'activation.

## 1. Préparer les fichiers d'environnement

1. S'assurer que `backend/.env.dev` (chargé par Django et par `poetry run`) contient la clé `OPENAI_API_KEY=<clé>` disposant de l'accès Assistants v2. C'est la source de vérité côté développement.
2. Laisser `backend/agents/.env` être géré par les scripts d'import : il sera créé automatiquement pour stocker les `*_ASSISTANT_ID`. Vous pouvez y dupliquer `OPENAI_API_KEY` si vous préférez, mais ce n'est plus requis tant que `.env.dev` est correctement chargé.【F:backend/agents/register_agent.py†L10-L89】

> Astuce : utiliser un compte de service dédié, stocker la clé dans un coffre et automatiser sa rotation.

## 2. Enregistrer les assistants OpenAI

1. Installer les dépendances listées dans `backend/agents/requirements.txt` (Poetry ou `pip install -r`).
2. Charger l'environnement avant d'exécuter le script, par exemple :

   ```bash
   set -a
   source backend/.env.dev
   set +a
   ```

   > Alternative : `poetry run python -m dotenv -f backend/.env.dev run -- python backend/agents/register_agent.py`
3. Exécuter `python backend/agents/register_agent.py` depuis la racine du dépôt :
   - Le script charge chaque profil JSON, tronque les champs aux limites supportées et appelle `openai.beta.assistants.create`.
   - Chaque nouvel ID (`*_ASSISTANT_ID`) est ajouté dans `backend/agents/.env` puis récapitulé dans `agents_registry.json` pour traçabilité.【F:backend/agents/register_agent.py†L49-L115】

> Si l'ID existe déjà dans `.env`, l'agent est ignoré pour éviter la réinscription.【F:backend/agents/register_agent.py†L59-L63】

## 3. Générer le registre de référence

Après enregistrement (ou en cas de modification manuelle du `.env` des agents), lancer `python backend/agents/generate_agents_registry.py` :

- Le script fusionne les JSON et injecte les IDs issus du `.env` dans `agents_registry.json`, utile pour les audits ou l'export vers d'autres services.【F:backend/agents/generate_agents_registry.py†L17-L64】

## 4. Importer les agents dans Django

Dans l'environnement virtuel backend (Poetry), exécuter :

```bash
poetry run python manage.py import_agents --dir backend/agents
```

La commande vérifie le schéma (`AGENT_SCHEMA`) puis met à jour/crée les objets `AgentProfile` avec l'intégralité du JSON comme métadonnée pour conserver la source de vérité.【F:backend/ai_assistants/management/commands/import_agents.py†L1-L55】

> Relancer la commande à chaque changement de manifeste JSON pour synchroniser la base.

## 5. Associer manifeste global et contextes

- Définir (via l'admin ou fixtures) un `Manifesto` marqué `current=True` afin que les appels puissent embarquer le manifeste commun.【F:backend/ai_assistants/utils/db_loader.py†L8-L81】
- Veiller à remplir `AgentSystemContext` pour chaque agent (sinon un message d'alerte est retourné).【F:backend/ai_assistants/utils/db_loader.py†L47-L57】

## 6. Vérifier l'activation applicative

- Les endpoints Django exposent la liste (`GET /api/agents/`) et les interactions (`POST /api/agents/<slug>/ask`). Vérifier qu'ils retournent bien les agents importés.
- Le client interne `ask_agent` combine manifeste, profil complet et contexte avant d'appeler l'assistant OpenAI identifié via `.env`. Toute absence d'ID génère une erreur explicite.【F:backend/ai_assistants/utils/team_client.py†L11-L92】

## 7. Checklist rapide

- [ ] `backend/.env.dev` contient `OPENAI_API_KEY` (et variantes pour les autres environnements).
- [ ] `backend/agents/.env` généré avec les `*_ASSISTANT_ID`.
- [ ] `register_agent.py` exécuté sans erreur.
- [ ] `generate_agents_registry.py` mis à jour.
- [ ] `manage.py import_agents` rejoué.
- [ ] `Manifesto` + `AgentSystemContext` renseignés.
- [ ] `POST /api/agents/<slug>/ask` répond avec une sortie modèle.

En suivant cette séquence, les agents définis dans le dépôt sont prêts à répondre via l'application et les intégrations internes tout en conservant une traçabilité complète des manifests et IDs.
