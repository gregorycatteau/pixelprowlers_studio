# E‑OTP — Audits Sécurité S7 — Synthèse consolidée

Objectif: consolider les résultats d’audit backend/frontend avant pré‑prod, tracer les corrections et décisions de risk‑acceptance éventuelles.

Métadonnées
- Périmètre: backend (Python/Poetry), frontend (Nuxt/Node)
- Commit/Tag analysé: <à renseigner>
- Date/Heure (UTC): <à renseigner>
- Responsables: <à renseigner>

Sources (rapports bruts)
- Backend
  - pip‑audit: docs/auth/eotp/audits/pip-audit.json (ou .md)
  - Bandit: docs/auth/eotp/audits/bandit.json
  - Safety: docs/auth/eotp/audits/safety.txt
- Frontend
  - npm audit: docs/auth/eotp/audits/npm-audit.json

Commandes d’exécution (référence)
- Backend:
  - poetry run pip-audit --fix --desc
  - poetry run bandit -r backend -f json -o docs/auth/eotp/audits/bandit.json
  - poetry run safety check -r backend/requirements-dev.txt > docs/auth/eotp/audits/safety.txt
- Frontend:
  - (cd frontend && npm audit --json > ../docs/auth/eotp/audits/npm-audit.json)
  - (cd frontend && npm update --force)  # si corrections mineures sans breaking change

Tableau de synthèse (avant → après)
| Outil       | Critique (avant→après) | Haute (avant→après) | Moyenne (avant→après) | Basse (avant→après) | Actions réalisées | Notes |
|-------------|-------------------------|----------------------|------------------------|---------------------|-------------------|-------|
| pip‑audit   | <A→B>                  | <A→B>               | <A→B>                 | <A→B>              | pin/upgrade, ignore CVE justifié | Réfs CVE: … |
| Bandit      | <A→B>                  | <A→B>               | <A→B>                 | <A→B>              | fix code/mute avec justification | Rules: … |
| Safety      | <A→B>                  | <A→B>               | <A→B>                 | <A→B>              | upgrade/constraints | … |
| npm audit   | <A→B>                  | <A→B>               | <A→B>                 | <A→B>              | update --force sélectif | Vérif build OK |

Détails et remédiations
- Dépendances mises à jour (backend):
  - paquet@version_old → paquet@version_new (raison/CVE: …, impact: …, tests OK: oui/non)
- Dépendances mises à jour (frontend):
  - paquet@version_old → paquet@version_new (raison/CVE: …, impact: …, build OK: oui/non)
- Corrections de code (Bandit):
  - Règle Bxxx: fichier.py:Lxx — correction appliquée / justification d’ignore avec commentaire précis
- Contrainte de version/Pin:
  - Ajout/ajustement de contraintes dans pyproject/requirements si nécessaire

Risk acceptance (le cas échéant)
- Vulnérabilité: <CVE/ID>
- Contexte: <usage limité, code non exploitable, environnement cloisonné, plan de retrait à S+1, etc.>
- Mesures compensatoires: <headers, CSP, permissions, réseau, monitoring>
- Échéance de correction: <date>
- Validation: <nom/équipe>

Validation Go‑Live (gate S7)
- Critiques: 0 résiduelles [ ] oui / [ ] non (si non → blocant Go‑Live)
- Hautes: 0 résiduelles ou acceptées avec dérogation formelle [ ] oui / [ ] non
- Preuves archivées (rapports bruts + ce fichier): [ ] oui
- Build/test (Pytest/Vitest/Playwright) au vert après remédiations: [ ] oui

Annexes
- Captures/outputs complémentaires: docs/auth/eotp/audits/
- Lien vers CHANGELOG S7: docs/auth/eotp/CHANGELOG-S7.md
- Lien checklist Go‑Live: docs/auth/eotp/GO-LIVE-CHECKLIST.md
