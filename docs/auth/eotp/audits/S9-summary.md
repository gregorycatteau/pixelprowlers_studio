# E‑OTP — Audits Sécurité S9 — Synthèse consolidée (final)

Objectif
- Consolider les résultats d’audit finaux (S9) après exécution des outils.
- Tracer les corrections, les pins/updates et les éventuelles acceptations de risque (avec échéance).
- Archiver les rapports bruts sous docs/auth/eotp/audits/.

Commandes d’exécution (référence)
- Backend:
  - poetry run pip-audit --fix --desc -f json -o docs/auth/eotp/audits/pip-audit.json
  - poetry run bandit -r backend -f json -o docs/auth/eotp/audits/bandit.json
  - poetry run safety check -r backend/requirements-dev.txt > docs/auth/eotp/audits/safety.txt
- Frontend:
  - (cd frontend && npm audit --json > ../docs/auth/eotp/audits/npm-audit.json)
  - (cd frontend && npm update --force)  # si corrections mineures non breaking
- Script helper:
  - bash tools/run_audit_ci.sh   # exécute les 4 audits et archive les rapports

Tableau de synthèse (avant → après)
| Outil       | Critique (A→B) | Haute (A→B) | Moyenne (A→B) | Basse (A→B) | Actions réalisées            | Notes / CVE |
|-------------|-----------------|-------------|---------------|-------------|------------------------------|-------------|
| pip‑audit   | <A→B>          | <A→B>       | <A→B>         | <A→B>       | pin/upgrade, ignore justifié | CVE-…       |
| Bandit      | <A→B>          | <A→B>       | <A→B>         | <A→B>       | fix code / mute justifié     | Bxxx        |
| Safety      | <A→B>          | <A→B>       | <A→B>         | <A→B>       | upgrade/constraints          |             |
| npm audit   | <A→B>          | <A→B>       | <A→B>         | <A→B>       | update --force sélectif      | build OK    |

Détails des remédiations
- Backend (deps):
  - paquet@v_old → paquet@v_new (raison/CVE: …, impact: …, tests OK: oui/non)
- Frontend (deps):
  - paquet@v_old → paquet@v_new (raison/CVE: …, impact: …, build OK: oui/non)
- Corrections code (Bandit):
  - Règle Bxxx: fichier.py:Lxx — correction / justification d’ignore documentée
- Contrainte de version:
  - Ajout/ajustement de pins (pyproject/requirements) et justification

Acceptations de risque (si nécessaires)
- Vulnérabilité: <CVE/ID>
- Contexte: <usage limité, code non exploitable, environnement cloisonné, plan de retrait S+1, etc.>
- Mesures compensatoires: <headers, CSP, permissions, réseau, monitoring>
- Échéance de correction: <date>
- Validation: <nom/équipe>

Validation finale (gate S9)
- Critiques résiduelles: 0 [ ] oui / [ ] non (si non → blocant)
- Hautes résiduelles: 0 ou dérogation formelle [ ] oui / [ ] non
- Preuves archivées (rapports bruts + ce fichier): [ ] oui
- Suites de tests (Pytest/Vitest/Playwright) au vert après remédiations: [ ] oui

Annexes
- Rapports bruts:
  - pip‑audit: docs/auth/eotp/audits/pip-audit.json (ou .md)
  - Bandit: docs/auth/eotp/audits/bandit.json
  - Safety: docs/auth/eotp/audits/safety.txt
  - npm audit: docs/auth/eotp/audits/npm-audit.json
- S9 tendances/monitoring:
  - tools/reports/trends/YYYY‑MM‑DD.json
  - tools/reports/trends/diff-YYYYMMDD.log (test_trends.sh)
- Références:
  - docs/auth/eotp/CHANGELOG-S9.md
  - docs/auth/eotp/09-feedback-loop.md
  - docs/auth/eotp/08-monitoring-intelligent.md
