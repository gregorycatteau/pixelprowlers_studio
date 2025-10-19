# E‑OTP — CHANGELOG S7 (Hardening Final & Go‑Live Readiness)

Objectif
- Verrouiller toute la surface e‑OTP avant passage en pré‑prod/Go‑Live.
- Tracer les décisions de durcissement, les preuves d’audits et la validation finale.

Périmètre
- Backend (Django)
- Frontend (Nuxt)
- Observabilité & Alerting
- Runbooks Ops

Résumé exécutif
- Durcissement sécurité appliqué (headers, cookies, CSP, secrets, Redis/Celery) — [ ] à compléter
- Audits sécurité exécutés et consolidés — [ ] à compléter
- Résilience testée (Redis/Postmark fallback, purge batch) — [ ] à compléter
- Runbooks packagés et validés — [ ] à compléter
- Go‑Live checklist satisfaisante — [ ] à compléter

Décisions de durcissement (A → Z)
1) Headers HTTP obligatoires
   - Strict‑Transport‑Security: max‑age=31536000; includeSubDomains [min]
   - X‑Content‑Type‑Options: nosniff
   - X‑Frame‑Options: DENY (ou SAMEORIGIN selon besoin backoffice)
   - Referrer‑Policy: no-referrer (ou strict-origin-when-cross-origin si besoin)
   - Permissions‑Policy: caméra/micro/geo désactivés par défaut
   - Content‑Security‑Policy (CSP minimal compatible Nuxt) — à documenter précisément
   Preuves: captures curl -I / Playwright — voir docs/auth/eotp/audits/

2) Cookies d’authentification et session
   - Flags: HttpOnly, Secure, SameSite=Strict
   - Durée de vie minimale et documentée
   - Vérifié via tests Pytest — [ ] à compléter

3) Secrets et rotation
   - EOTP_PEPPER, PASS_PEPPER, POSTMARK_WEBHOOK_SECRET
   - Secrets distincts par environnement, non commités (vault/CI)
   - Plan de rotation semestriel documenté dans runbook rotate_pepper.md
   - Test de rotation simulé (test_env_secrets_rotation) — [ ] à compléter

4) Redis & Celery
   - Mot de passe Redis requis
   - TLS activé si disponible
   - TTLs vérifiés (tasks/keys)
   - Procédures de relance documentées (celery‑beat‑purge.md)
   - Fallback metrics in‑memory quand Redis down — [ ] à compléter

5) CSRF, Sessions, Endpoints debug
   - CSRF activé partout
   - Cookies de session conformes
   - Endpoints /debug interdits en prod (assert APP_ENV) — [ ] à compléter

6) Journal d’audit append‑only et hash‑chain
   - verify_log_chain.py --deep OK — [ ] à compléter

Audits sécurité — résultats consolidés
- Sources brutes:
  - pip‑audit: docs/auth/eotp/audits/pip-audit.json (ou .md)
  - Bandit: docs/auth/eotp/audits/bandit.json
  - Safety: docs/auth/eotp/audits/safety.txt
  - npm audit: docs/auth/eotp/audits/npm-audit.json
- Synthèse: docs/auth/eotp/audits/S7-summary.md

Tableau de synthèse (avant → après)
| Outil       | Critique (A→B) | Haute (A→B) | Moyenne (A→B) | Basse (A→B) | Actions | Notes |
|-------------|-----------------|-------------|---------------|-------------|--------|-------|
| pip‑audit   | <A→B>          | <A→B>       | <A→B>         | <A→B>       | pin/upgrade | refs CVE |
| Bandit      | <A→B>          | <A→B>       | <A→B>         | <A→B>       | fix/mute justifié | rules |
| Safety      | <A→B>          | <A→B>       | <A→B>         | <A→B>       | upgrade/constraints |  |
| npm audit   | <A→B>          | <A→B>       | <A→B>         | <A→B>       | update --force | build OK |

Résilience & Chaos (léger)
- tools/test_resilience.sh (journal: tools/reports/resilience.log)
- Scénarios:
  - Redis down → fallback metrics adapter in‑memory → OK — [ ] à compléter
  - eotp_purge_expired batch ~10k → pas d’erreur — [ ] à compléter
  - Postmark 5xx simulés → fallback SMTP opérationnel — [ ] à compléter

Observabilité & Alerting
- tools/obs_sanity.sh → aucune alerte CRIT simulée — [ ] à compléter
- ops/alerts.json: WARN/CRIT < 5% sur 1h (seuils validés) — [ ] à compléter
- Hash‑chain et ancrage: OK — [ ] à compléter

Fichiers & PRs notables
- ops/alerts.schema.json: compatibilité validateur (draft‑07)
- docs/auth/eotp/GO-LIVE-CHECKLIST.md: checklist Go‑Live
- docs/auth/eotp/audits/S7-summary.md: synthèse auditable
- docs/auth/eotp/runbooks/runbook-audit.md: relance audits & critères
- runbooks: process.md, rotate_pepper.md, celery-beat-purge.md mis à jour
- Scripts: tools/test_resilience.sh (nouveau)

Go‑Live Checklist — statut
Voir: docs/auth/eotp/GO-LIVE-CHECKLIST.md
- Audits: [ ] OK
- Durcissement infra: [ ] OK
- Résilience: [ ] OK
- Runbooks: [ ] OK
- Observabilité/Alerting: [ ] OK
- Suites de tests (Pytest/Vitest/Playwright): [ ] OK
- Désactivation /debug en prod: [ ] OK
- Hash‑chain & verify_log_chain.py --deep: [ ] OK

Preuves (à attacher/archiver)
- Captures headers (curl -I / PW)
- Rapports pip‑audit, Bandit, Safety, npm audit
- Sortie tools/obs_sanity.sh
- Logs tools/reports/resilience.log

Annexes
- Ordre de lecture:
  - docs/auth/eotp/todos/todo-S7.md
  - docs/auth/eotp/07-observabilite-alerting.md
  - docs/auth/eotp/rapport-final-eotp.md
- Runbooks:
  - docs/auth/eotp/runbooks/process.md
  - docs/auth/eotp/runbooks/rotate_pepper.md
  - docs/auth/eotp/runbooks/celery-beat-purge.md
  - docs/auth/eotp/runbooks/runbook-audit.md

Signature & validation
- Pré‑prod prête: [ ] oui / [ ] non
- Go‑Live validé: [ ] oui / [ ] non
- Validateurs: <noms/équipes>
- Date: <YYYY‑MM‑DD>
