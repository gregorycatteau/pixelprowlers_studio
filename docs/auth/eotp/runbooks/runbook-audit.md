# Runbook — Audits Sécurité (S7)

Objectif
- Décrire comment exécuter les audits backend/frontend, archiver les rapports, consolider une synthèse et décider des remédiations avant pré‑prod/Go‑Live.

Périmètre
- Backend (Python/Poetry) — dépendances et patterns de code
- Frontend (Nuxt/Node) — dépendances
- Consolidation des résultats et décisions (risk acceptance si nécessaire)

Pré‑requis
- Python/Poetry installés, environnement virtual activé si applicable
- Node/npm installés (frontend)
- Accès au repo, branche S7
- Répertoires d’audit existants (créés au besoin):
  - docs/auth/eotp/audits/
- Droits d’écriture dans docs/auth/eotp/audits/

Chemins et artifacts
- Backend:
  - Bandit JSON: docs/auth/eotp/audits/bandit.json
  - pip‑audit JSON/MD: docs/auth/eotp/audits/pip-audit.json (ou .md si format texte)
  - Safety TXT: docs/auth/eotp/audits/safety.txt
- Frontend:
  - npm audit JSON: docs/auth/eotp/audits/npm-audit.json
- Synthèse consolidée:
  - docs/auth/eotp/audits/S7-summary.md

Procédure — Backend
1) pip‑audit (audit de vulnérabilités Python)
   - Commande:
     poetry run pip-audit --fix --desc > docs/auth/eotp/audits/pip-audit.json
   - Si le format JSON direct n’est pas stable, rediriger vers .md:
     poetry run pip-audit --fix --desc > docs/auth/eotp/audits/pip-audit.md
   - Interprétation: vérifier le nombre de vulnérabilités avant/après, CVE listées, remédiations proposées.

2) Bandit (audit patterns de sécurité)
   - Commande:
     poetry run bandit -r backend -f json -o docs/auth/eotp/audits/bandit.json
   - Interprétation: cibler findings de sévérité MED/HIGH. Corriger le code ou documenter les justifications d’ignore (avec commentaire précis en code).

3) Safety (audit dépendances Python)
   - Commande:
     poetry run safety check -r backend/requirements-dev.txt > docs/auth/eotp/audits/safety.txt
   - Variante si besoin:
     poetry run safety check -r backend/requirements-dev.lock > docs/auth/eotp/audits/safety.txt
   - Interprétation: lister les paquets et CVE, proposer upgrade/pin.

Procédure — Frontend
1) npm audit
   - Commandes:
     cd frontend
     npm audit --json > ../docs/auth/eotp/audits/npm-audit.json
   - Remédiations mineures si non breaking:
     npm update --force
   - Re‑exécuter npm audit et mettre à jour le rapport.

Consolidation — S7-summary.md
- Ouvrir docs/auth/eotp/audits/S7-summary.md
- Renseigner métadonnées (commit/tag, date, responsables)
- Compléter le tableau « avant → après »
- Lister actions réalisées (pins/upgrades), corrections de code (Bandit) et éventuelles justifications d’ignore
- Documenter toute « risk acceptance » (CVE, contexte, mesures compensatoires, échéance, validation)

Critères de sortie (Gate S7)
- Vulnérabilités critiques résiduelles: 0 (sinon blocant)
- Vulnérabilités hautes résiduelles: 0 ou dérogation formelle avec plan de retrait et mesures compensatoires
- Rapports archivés et liens présents dans S7-summary.md
- Build/tests (Pytest/Vitest/Playwright) verts après remédiations

Intégration CI (suggestion)
- Jobs CI séparés pour:
  - pip‑audit (fail si critiques)
  - Bandit (fail si HIGH non justifiées)
  - Safety (fail si seuil critique)
  - npm audit (fail si severity >= high)
- Publication des artifacts en sortie de pipeline vers docs/auth/eotp/audits/ (ou storage externe), puis commit de S7-summary.md mise à jour

Bonnes pratiques
- Toujours lier une remédiation à une référence (CVE/issue)
- Documenter les pins et leurs raisons dans pyproject/requirements et CHANGELOG-S7.md
- Re‑lancer la suite de tests après chaque vague d’upgrades
- En cas d’ignore, ajouter un commentaire explicite dans le code (Bandit) et la justification dans S7-summary.md

Liens utiles
- Synthèse: docs/auth/eotp/audits/S7-summary.md
- Checklist Go‑Live: docs/auth/eotp/GO-LIVE-CHECKLIST.md
- Changelog S7: docs/auth/eotp/CHANGELOG-S7.md
