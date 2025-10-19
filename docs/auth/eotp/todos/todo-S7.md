# Todo — Sprint S7 (Hardening final & Definition of Done)
Status: DRAFT
Sprint: S7
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 06 — Plan migrations & rollback: ../06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ../08-mail-transport-et-dns.md
- 09 — UX spec e‑OTP: ../09-ux-spec-eotp.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md
- CHANGELOG Sprint 0: ../CHANGELOG-S0.md

Objectif du sprint
- Atteindre la Definition of Done globale: stabilité, sécurité et qualité “tout vert” (Pytest/Vitest/Playwright) avec seuils de couverture, observabilité opérationnelle (dashboards/alertes), runbooks et rollback rehearsals validés, documentation finale consolidée.
- Réaliser les tests d’intrusion ciblés (angle “hacker”) et corriger les derniers points avant Go‑Live contrôlé par feature flags.

Checklist technique (append‑only)
Backend (Django)
- ⏳ Revue finale services e‑OTP (issue/verify/resend): nettoyage TODO/WARN, invariants et transitions d’état audités — [02][03]
  Acceptation: aucun log sensible; invariants documentés (one‑time, TTL, context); lints/ruff OK.
- ⏳ Argon2id: valider paramètres définitifs (m=64MiB, t=3, p=2 ou ajuste) + note de capacité CPU — [06][05]
  Acceptation: bench léger; doc finalisée; métriques p95/99 sous seuil.
- ⏳ Constant‑time compare: vérification systématique sur verify/gate — [03]
  Acceptation: tests unitaires couvrent; code audité.
- ⏳ Pepper rotation rehearsal: rédiger et tester “rotate_pepper.md” (dry‑run) — [10]
  Acceptation: runbook rédigé; sandbox validé; aucun secret en clair.

Frontend (Nuxt)
- ⏳ UX polish /login/2fa et Gate: wording, a11y (aria‑live, focus), mode sombre stabilisé — [09]
  Acceptation: revue a11y basique passe; data‑testid listée; aucun anti‑pattern SSR.
- ⏳ i18n/FR final: messages uniformes, pas de fuite d’état (invalid vs expired) — [09][03]
  Acceptation: revu; capture textuelle dans doc.

Tests (QA)
- ⏳ Pytest (backend): couverture globale (ligne/branche) atteint seuils repo + module e‑OTP L≥85%, B≥75% — [05]
  Acceptation: rapports coverage XML; gates CI “green”.
- ⏳ Vitest (frontend): L≥80% dossiers e‑OTP — [05]
  Acceptation: rapports coverage; tests stables.
- ⏳ Playwright (E2E) — 3 navigateurs:
  - Happy path (login→2FA→gate→console)
  - Invalid / Expired / Resend cooldown / Locked
  - CSRF manquant = 403, Nonce replay = 400 (sanity) — [05]
  Acceptation: flakiness ≤ 1%; retries ciblés OK; reports HTML archivés.
- ⏳ Fuzz / Chaos tests légers endpoints verify/resend (inputs inattendus, délais) — [03][05]
  Acceptation: aucune régression/crash; garde-fous actifs (429/400).

Sécurité / Pentests ciblés (angle “hacker”)
- ⏳ Brute‑force OTP (balayage codes) — doit être stoppé par rate‑limits/backoff — [03][04]
  Acceptation: 429/locked selon politiques; aucun 200 inattendu.
- ⏳ Replay OTP après succès — [03]
  Acceptation: invalid_code uniforme; no info leak.
- ⏳ CSRF bypass tentatives — [03]
  Acceptation: 403 sans X‑CSRFToken; plugin fetch‑auth et proxy OK.
- ⏳ Nonce replay sur endpoints mutatifs cibles — [03]
  Acceptation: 400 nonce_replay; X‑New‑Request‑Nonce cycle actif.
- ⏳ Enumeration état (invalid vs expired) — [03][09]
  Acceptation: messages UI génériques; logs/metrics internes OK.

Observabilité
- ⏳ Dashboards finaux (Funnel, Fiabilité, Sécurité/Abus, Délivrabilité) — [07]
  Acceptation: panels à jour; captures anonymisées; variables realm.
- ⏳ Alertes finies (success<70% CRIT, locked>10% CRIT, 429 spikes WARN/CRIT, hard bounce>3%/h CRIT) — [07]
  Acceptation: règles testées en sandbox; mute window déploiements; hysteresis.
- ⏳ Journal inviolable: validation hash chain (échantillon) + export ancres — [07]
  Acceptation: utilitaire de vérification passe; doc usage.

Ops (SRE)
- ⏳ Rollback rehearsal (flags OFF, comportement legacy) — [06]
  Acceptation: désactivation e‑OTP par realm sans impact; plan de retour consigné.
- ⏳ Backups/restores rapides (sanity DB) — [06]
  Acceptation: test restore en stage; aucun secret en clair.
- ⏳ runbook-process.md final (alerte→action→ticket→clôture), Owners par risque — [10]
  Acceptation: docs à jour; liens depuis index todos.

Critères d’acceptation (DoD S7)
- CI verte: Pytest/Vitest/Playwright “tout vert” avec seuils coverage atteints.
- Pentests ciblés passent (aucun finding bloquant); logs PII‑safe; grep secrets = 0.
- Dashboards/alertes opérationnels; hash chain validée; runbooks prêts; rollback rehearsals OK.
- Documentation finale revue (S0 + runbooks + rotate_pepper.md), liens vérifiés.

Dépendances
- S1–S6 complétés (endpoints, UX, throttling, observabilité).
- Accès à environnements de stage/test avec Redis/Provider mail.

Risques spécifiques (S7) & mitigation
- 🔒 Flakiness E2E cross‑browser — Mitigation: selectors robustes, retry unique, WaitForURL/heading; rapporter flakys. Ref: [05].
- 🔒 Alerte bruyante en prod — Mitigation: hystérésis, tuning, anti‑spam notifications; runbook process. Ref: [07][10].
- 🔒 Régressions tardives sécurité — Mitigation: suite pentests automatisée en CI “security” (option nightly). Ref: [03][10].

Tests & validation — commandes
- Backend:
  - pytest -q --maxfail=1 --cov --cov-report=xml
- Frontend:
  - cd frontend && npx vitest run --coverage
  - cd frontend && npx playwright test
- Audit sécurité (scripts E2E)
  - cd frontend && npx playwright test test-e2e/dojo-security.spec.ts
- Critère “green”: 100% des suites passent; seuils coverage atteints.

Documentation / Appendices
- Mettre à jour: [05] (seuils finaux), [07] (captures dashboards, export alert rules), [10] (Owners assignés), rotate_pepper.md (nouveau runbook).
- Append later: rapport récapitulatif S7 (traces verif hash chain, captures, indicateurs finaux).

Notes techniques confirmées à intégrer (rappel)
- Logs PII‑safe; aucune valeur OTP/email/cookie en clair.
- Flags par realm: activation progressive; rollback simple via flags.
- Seuils critiques: success<70% CRIT, locked>10% CRIT, hard bounce>3%/h CRIT.
- Argon2id+pepper; constant‑time compare partout nécessaire.

Append‑only
- Ne pas supprimer; append des sous‑tâches/observations datées (journal).
