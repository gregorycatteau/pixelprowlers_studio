# Todo — Sprint S1 (Backend Core e‑OTP)
Status: DRAFT
Sprint: S1
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 06 — Plan migrations & rollback: ../06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 09 — UX spec e‑OTP: ../09-ux-spec-eotp.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif du sprint
- Livrer le noyau backend e‑OTP: modèle/migrations eotp_challenge, services issue/verify/resend, endpoints, purge TTL (Celery beat), feature flags et instrumentation de base.
- Aucune dépendance à l’envoi réel d’email (provider géré en S2). En test, l’endpoint _peek est disponible (APP_ENV=test).

Checklist technique (append‑only)
Backend (Django)
- ⏳ Modèle DB eotp_challenge (UUID PK, session_key, status, code_hash Argon2id, pepper_id, tries_count, resend_count, created_at, expires_at, last_sent_at, context_ua, context_ip_prefix, corr_id) — [02] — Acceptation: migrations passent; contraintes CHECK; index (session_key), (status, expires_at), (user_id, created_at). Dép: DB OK.
- ⏳ Migration initiale + type status (varchar+CHECK) — [06] — Acceptation: migrate ok, rollback ok. Dép: modèle figé.
- ⏳ Constraint multi‑device: documenter et décider (désactiver UNIQUE(session_key,status='pending') ou ajouter device_hash opt.) — [06][02] — Acceptation: règle appliquée et testée. Dép: UX/S3 pour device.
- ⏳ Services eotp_issue (secret 128b, code 6/8, Argon2id+pepper, TTL, status=pending) — [02] — Acceptation: tests unitaires ok; code non loggué.
- ⏳ Services eotp_verify (constant‑time compare, transitions consumed/locked, tries_count, contexte UA/IP tolérant par flag) — [02][03] — Acceptation: tests unitaires ok; anti‑rejeu vérifié.
- ⏳ Services eotp_resend (quota minimal S1 + cooldown court; invalider code précédent et régénérer) — [02][03] — Acceptation: tests unitaires ok; Retry‑After défini.
- ⏳ Endpoints REST: POST /api/auth/2fa/email/verify/, /resend/, (test‑only) /_peek/ — CSRF protect — [02][03] — Acceptation: DRF/CSRF en place; _peek accessible uniquement en APP_ENV=test.
- ⏳ Feature flags: eotp_enabled, eotp_code_length, eotp_strict_context, eotp_cooldown_profile (lecture côté backend) — [02][06] — Acceptation: flags chargeables via settings/env.
- ⏳ Purge TTL via Celery beat: management command eotp_purge_expired + planification — [06] — Acceptation: purge OK; VACUUM ANALYZE lancé post‑purge.
- ⏳ Argon2id calibrage: m=64MiB, t=3, p=2 (base) + documentation des paramètres — [06] — Acceptation: note de capacité + tests de perf basiques.
- ⏳ Isolation realms: garantir non‑réutilisation session_key cross‑realm (tests) — [02] — Acceptation: tests d’intégration passent.

Front (Nuxt) — impact minimal S1
- ⏳ Verrouiller l’usage d’_peek uniquement en E2E/test (config côté proxy déjà en place) — [01][02] — Acceptation: tests Playwright happy path OK.

Tests (QA)
- ⏳ Pytest unitaires: services issue/verify/resend, constraints DB — [05] — Acceptation: L≥85% sur module e‑OTP; tests listés ci‑dessous OK.
- ⏳ Pytest intégration: endpoints + CSRF (403 si manquant), TTL/expired, anti‑rejeu — [05] — Acceptation: 100% des cas décrits OK.
- ⏳ Playwright (dev/test): eotp‑happy.spec (déjà présent) — [05] — Acceptation: vert avec APP_ENV=test; E2E_USER/PASS fournis.
- ⏳ Vitest: N/A S1 (composants en S3) — [05] — Acceptation: N/A.

Observabilité
- ⏳ Événements: auth:eotp_issued|resent|ok|failed|expired|locked (payload PII‑safe) — [07] — Acceptation: events émis; corrélation X‑Request‑ID/Corr_ID.
- ⏳ Métriques: compteurs eotp_* et latences basiques (issue→ok) — [07] — Acceptation: métriques visibles en dev/test.
- ⏳ Logs: PII‑safe (aucun email/code en clair), niveaux INFO — [07][03] — Acceptation: grep de non‑régression ok.

Ops (SRE)
- ⏳ Celery beat activation (profil dev/test) — [06] — Acceptation: planification purge visible dans logs.
- ⏳ Runbook de purge et monitoring backlog pending — [06][07] — Acceptation: doc minimale ajoutée.

Critères d’acceptation (DoD S1)
- Pytest green (unit+integ e‑OTP); couverture L≥85% sur module e‑OTP.
- Endpoints verify/resend/_peek opérationnels (CSRF ok), sans fuite de PII.
- Purge TTL opérationnelle via Celery beat + VACUUM ANALYZE post‑purge.
- Flags e‑OTP actifs (lecture/contrôle).
- Événements/métriques de base émis; corrélation request_id présente.
- Aucun changement côté UI au‑delà du nécessaire pour E2E test (proxy déjà conforme).

Dépendances
- DB/Poetry/Celery opérationnels en environnement dev/test.
- S2 (Mail): abstraction provider et DNS, non requis pour S1 (peek pour tests).
- S3 (UX): consommera verify/resend; dépend de S1 endpoints.

Risques spécifiques (S1) & mitigation
- 🔒 Charge CPU Argon2id mal calibrée — Mitigation: m/t/p base + bench; ajustement rapide et doc capacité. Ref: [10].
- 🔒 Faux positifs UA/IP — Mitigation: flags permissifs par défaut; logs “low confidence”. Ref: [10].
- 🔒 Purge inactive (accumulation) — Mitigation: beat ON + alerte backlog + VACUUM. Ref: [10].
- 🔒 Régression CSRF — Mitigation: tests intégration + E2E 403 existants. Ref: [10].

Tests & validation — commandes
- Pytest (backend):
  - pytest -q
- Playwright (frontend E2E):
  - cd frontend && npx playwright test test-e2e/eotp-happy.spec.ts
- Critère “green”: l’ensemble des suites ci‑dessus doivent passer.

Jeu de tests (référence minimale Pytest)
- test_issue_cree_challenge_pending_avec_hash_argon2id
- test_verify_code_valide_change_status_en_consumed_et_bloque_rejeu
- test_verify_code_invalide_incremente_tries_et_applique_backoff
- test_resend_invalide_ancien_code_et_regenere_avec_cooldown
- test_csrf_obligatoire_sur_verify_resend_403
- test_purge_supprime_expired_et_analyse_post_purge
- test_events_emis_sans_exposer_code_ou_email
- test_isolation_realms_session_key

Documentation / Appendices
- Mettre à jour: [06] (retours migration), [07] (événements/métriques), [02] (détails paramètres Argon2id).
- Append later: ajouter captures anonymisées de métriques dev/test; noter les valeurs m/t/p finales retenues.

Notes techniques confirmées à intégrer (rappel)
- Hash: Argon2id + pepper séparée (EOTP_PEPPER).
- Calibrage de base: m=64 MiB, t=3, p=2.
- Jobs: purge TTL via Celery beat (pas de cron system).
- VACUUM ANALYZE eotp_challenge post‑purge (intégré à la commande).
- Constant‑time compare obligatoire.
- Isolation realms: aucune session_key réutilisable cross‑realm.

Append‑only
- Ne pas supprimer les entrées; ajouter de nouvelles lignes ou sous‑tâches avec date/initiales si besoin (journal interne).
