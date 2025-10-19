# E-OTP — GO-LIVE CHECKLIST (S7)

Objectif: Valider le durcissement final, la conformité sécurité et la résilience avant pré‑prod/Go‑Live.

Statut global:
- [ ] Pré‑prod prête
- [ ] Go‑Live validé

1) Pré‑requis
- [ ] Lecture préalable effectuée
  - [ ] docs/auth/eotp/todos/todo-S7.md
  - [ ] docs/auth/eotp/CHANGELOG-S6.md
  - [ ] docs/auth/eotp/07-observabilite-alerting.md (S4→S6→S7)
  - [ ] docs/auth/eotp/rapport-final-eotp.md (annexes hash-chain, ancrage, risk logs)
  - [ ] docs/auth/eotp/runbooks/*.md (rotate_pepper, celery-beat-purge, process)
- [ ] Variables d’environnement chargées pour pré‑prod
- [ ] Secrets disponibles (vault/CI/CD) et non commités

2) Audits de sécurité (S7)
Backend
- [ ] pip-audit exécuté et corrigé (si possible)
  - Commande: poetry run pip-audit --fix --desc
  - [ ] Rapport archivé: docs/auth/eotp/audits/pip-audit.json (ou .md)
- [ ] Bandit exécuté
  - Commande: poetry run bandit -r backend -f json -o docs/auth/eotp/audits/bandit.json
  - [ ] Rapport archivé
- [ ] Safety (dépendances) exécuté
  - Commande: poetry run safety check -r backend/requirements-dev.txt
  - [ ] Rapport archivé: docs/auth/eotp/audits/safety.txt

Frontend
- [ ] npm audit exécuté
  - Commande: (cd frontend && npm audit --json > ../docs/auth/eotp/audits/npm-audit.json)
  - [ ] Rapport archivé
- [ ] Mises à jour mineures forcées si OK
  - Commande: (cd frontend && npm update --force)

Synthèse
- [ ] docs/auth/eotp/audits/S7-summary.md renseigné avec tableau « avant → après » et décisions

3) Durcissement infrastructure
Headers HTTP
- [ ] Strict-Transport-Security
- [ ] X-Content-Type-Options
- [ ] X-Frame-Options
- [ ] Referrer-Policy
- [ ] Permissions-Policy
- [ ] Content-Security-Policy (CSP minimal compatible Nuxt)
Preuves:
- [ ] Captures/outputs (curl -I, Playwright) ajoutées dans docs/auth/eotp/audits/

Cookies
- [ ] HttpOnly
- [ ] Secure
- [ ] SameSite=Strict
- [ ] Durée minimale documentée

Secrets (.env)
- [ ] Plan de rotation validé (EOTP_PEPPER, PASS_PEPPER, POSTMARK_WEBHOOK_SECRET)
- [ ] Valeurs distinctes par environnement
- [ ] Stockage sécurisé (vault/CI/CD), non commitées
- [ ] Procédure runbook « rotate_pepper » à jour

Redis & Celery
- [ ] Mot de passe obligatoire
- [ ] TLS si disponible
- [ ] TTLs vérifiés (tasks/keys)
- [ ] Procédure de relance documentée

CSRF/Session
- [ ] CSRF activé partout (middleware + tests OK)
- [ ] Cookies de session conformes (secure, httponly, samesite)
- [ ] Aucun endpoint /debug accessible en prod

4) Résilience & Chaos (léger)
Script
- [ ] tools/test_resilience.sh créé et exécutable
- [ ] Journal: tools/reports/resilience.log

Scénarios
- [ ] Simulation Redis down → fallback metrics adapter in‑memory OK (pas de crash, logs explicites)
- [ ] eotp_purge_expired sous charge (batch ~10k) → pas d’erreur, temps raisonnables
- [ ] Postmark 5xx simulés → fallback SMTP opérationnel

5) Observabilité & Alerting
- [ ] tools/obs_sanity.sh renvoie zéro alerte CRIT simulée
- [ ] ops/alerts.json → WARN/CRIT < 5% sur 1h (seuils validés)
- [ ] Journal hash‑chain intègre (verify_log_chain.py --deep)
- [ ] Export des rapports d’audit/obs dans docs/auth/eotp/audits/

6) Tests à livrer (et à passer)
Pytest (backend)
- [ ] test_env_secrets_rotation() — simulateur de changement EOTP_PEPPER + vérifs hashées
- [ ] test_headers_present_and_strict() — GET → headers sécu attendus
- [ ] test_metrics_fallback_when_redis_down() — Redis off → in‑memory adapter expose stats
- [ ] test_log_chain_integrity() — détection corruption hash‑chain

Vitest/Playwright (frontend)
- [ ] Suites existantes au vert (CI locale)

7) Packaging Runbooks
docs/auth/eotp/runbooks/
- [ ] process.md — workflow alerte → diagnostic → mitigation → clôture
- [ ] rotate_pepper.md — dates de rotation semestrielle à jour
- [ ] celery-beat-purge.md — TTL + procédure manuelle de relance révisées
- [ ] runbook-audit.md — comment relancer les audits & valider avant merge

8) Documentation Go‑Live
- [ ] docs/auth/eotp/CHANGELOG-S7.md
  - Décisions de durcissement, rotations de secrets, audits OK
  - Captures/rapports: pip-audit, npm audit, bandit
  - Rapport obs_sanity.sh (toutes alertes OK)
- [ ] docs/auth/eotp/audits/S7-summary.md finalisé

9) Conformité & Sécurité
- [ ] Aucune fuite PII (grep/logging, redaction)
- [ ] Journal append‑only vérifié
- [ ] Endpoints /debug interdits en prod (assert APP_ENV)
- [ ] CSRF partout
- [ ] Secrets uniques, rotatifs, non commités
- [ ] Headers sécu présents sur toutes les routes

10) Validation finale
- [ ] Toutes les suites de tests (Pytest/Vitest/Playwright) ✅
- [ ] /debug/eotp-stats désactivé en prod
- [ ] Headers + CSP vérifiés (preuves archivées)
- [ ] Rotation secrets appliquée (preuves/horodatage)
- [ ] Runbooks validés (secops)
- [ ] Alerts < 5% WARN/CRIT sur 1h (pré‑prod)
- [ ] Hash‑chain OK (tools/verify_log_chain.py --deep)

Annexes
- Références:
  - docs/auth/eotp/todos/todo-S7.md
  - docs/auth/eotp/07-observabilite-alerting.md
  - docs/auth/eotp/rapport-final-eotp.md
  - ops/alerts.json / ops/alerts.schema.json (validation)
