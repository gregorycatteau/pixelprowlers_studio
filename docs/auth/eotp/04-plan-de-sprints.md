# 04 — Plan de sprints (1 → 7)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Principes d’organisation
2. Vue macro (enchaînement et dépendances)
3. Sprint 1 — Backend Core e‑OTP
4. Sprint 2 — Mailer & Domaine (SPF/DKIM/DMARC)
5. Sprint 3 — Front UX e‑OTP (Nuxt)
6. Sprint 4 — Throttling & Résilience (sans Turnstile)
7. Sprint 5 — Gate & Passphrase
8. Sprint 6 — Observabilité & Alerting
9. Sprint 7 — Hardening final & DoD global
10. Risques transverses et plans de mitigation
11. Références internes

1) Principes d’organisation
- Timebox par sprint: 1–2 semaines (à ajuster).
- Incréments “activables” via feature flags (désactivation rapide possible).
- Tests en continu (Pytest/Vitest/Playwright) + CI verte à la fin de chaque sprint.
- Sécurité dès la conception: aucun secret en clair, pas de logs sensibles, contrôles CSRF/nonce.
- Environnement: dev/test/prod ségrégués, APP_ENV=test pour E2E peek.

2) Vue macro (enchaînement et dépendances)
- S1 (fondations backend) → prérequis de S3/S4.
- S2 (email & DNS) peut se faire en parallèle de S3 si mocks/stubs côté tests; mais pour prod, S2 doit être done avant go‑live e‑OTP.
- S4 dépend partiellement de S1 (endpoints) et s’ajoute aux contrôles.
- S5 (gate/passphrase) construit sur S3.
- S6 (observabilité) se branche sur événements introduits S1–S4.
- S7 (hardening) finalise la qualité et le rollback rehearsals.

3) Sprint 1 — Backend Core e‑OTP
Objectifs
- Formaliser le modèle de données eotp_challenge (cf. 02‑architecture‑cible.md).
- Services issue/verify/resend (Argon2id + pepper séparée, TTL, statuts pending/consumed/expired/locked).
- Endpoints REST:
  - POST /api/auth/2fa/email/verify/
  - POST /api/auth/2fa/email/resend/
  - (test‑only) POST /api/auth/2fa/email/_peek/ (APP_ENV=test)
- Purge TTL (management command + cron/Celery beat).
- Feature flags eotp_enabled (par realm) et eotp_code_length, eotp_strict_context.

Tâches
- Migrations: table eotp_challenge + index (session_key, status+expires_at, user+created_at).
- Implémenter hashing Argon2id + pepper_id (pepper via env EOTP_PEPPER).
- Service issue(): génération secret 128 bits + code utilisateur (6/8 digits), status= pending.
- Service verify(): constant‑time compare, transitions d’état, liaison contexte (session/UA/IP).
- Service resend(): quotas de base + cooldown minimal (côté S1), invalider code précédent.
- Intégration logging/metrics: record_auth_event(eotp_*).
- Pytest: unit (services), integ (endpoints, TTL/purge).
- Documentation d’admin (feature flags, commandes de purge).

Dépendances
- PostgreSQL/DB opérationnelle; Celery beat (ou cron) pour purge.

Risques
- Charge Argon2id calibrage; collisions de sessions rares; migration DB sans downtime.

Critères de fin (DoD S1)
- Pytest green (services e‑OTP + endpoints), couverture minimale 80% sur module e‑OTP.
- Endpoints stables avec CSRF protect; feature flags opérationnels.
- Purge TTL exécutée en dev/test (preuve via logs/metrics).

Livrables
- Code backend (modèle, services, endpoints), migrations, doc admin, tests Pytest.

4) Sprint 2 — Mailer & Domaine (SPF/DKIM/DMARC)
Objectifs
- Abstraction mail provider (Postmark/Sendgrid) + fallback SMTP robuste (fail_silently=false en prod).
- Templates d’email e‑OTP minimalistes (pas de PII ni de liens sensibles).
- Documentation DNS: SPF/DKIM/DMARC, MTA‑STS, TLSRPT (checklist pixelprowlers.io).
- Gestion des bounces (hard/soft): collecte (webhook/smtp), métriques de base.

Tâches
- Interface Mailer + impl. provider (ou stub en dev/test) + fallback SMTP.
- Paramètres sender, Reply‑To, en‑têtes anti‑phishing (ex: X‑PPW‑Watermark).
- Webhook bounces (ou boîte aux lettres retour) → stockage minimal + métriques.
- CI: smoke mail (en dev: stub), tests d’intégration (mocks).
- Doc DNS (08‑mail‑transport‑et‑dns.md) + scripts de vérification manuelle (tools/ optionnel).

Dépendances
- Compte provider + zone DNS sous contrôle.

Risques
- Délivrabilité (réputation domaine), délais DNS, taux de bounces.

Critères de fin (DoD S2)
- En dev/test: envoi via stub OK; en stage/prod: vérifications DNS “pass”.
- Métriques bounces visibles (compteurs); aucune fuite de PII dans contenus.

Livrables
- Abstraction mail, doc DNS validée, tests d’intégration, métriques bounces.

5) Sprint 3 — Front UX e‑OTP (Nuxt)
Objectifs
- Écrans /login/2fa accessibles et robustes (a11y, mobile).
- Normalisation saisie (digits only), timer TTL, bouton resend (cooldown).
- Intégration composables existants (useAuth, useCsrf, useNonce) + proxies.

Tâches
- Pages/Composants: Login2FAView, CodeInput, ResendButton, Timer.
- États/Erreurs: invalid_code, locked, expired, 429 (Retry‑After).
- Vitest: tests de composants (formatage, timers, états).
- Playwright: “happy path” + erreurs usuelles.
- I18n (au moins FR), messages clairs.

Dépendances
- Endpoints S1; mail stub S2 pour E2E en stage.

Risques
- Hydratation SSR (garder patterns existants); UX cooldowns/lisibilité.

Critères de fin (DoD S3)
- Vitest > 80% sur composants e‑OTP; Playwright “happy path” vert.
- Accessibilité: labels, focus, ARIA live pour erreurs/cooldowns.

Livrables
- UI e‑OTP, tests Vitest, scénarios E2E Playwright.

6) Sprint 4 — Throttling & Résilience (sans Turnstile)
Objectifs
- Rate‑limits côté Django/Redis (verify/resend, par IP/compte/session).
- Backoff progressif, tarpit contrôlé; anti‑rejeu strict confirmé.
- Hooks sécurité session/CSRF/cookies consolidés.

Tâches
- Stockage Redis: clés ratelimit:eotp:(verify|resend):{sess|user|ip}.
- Politique quotas: ex. verify 6/10min session + 10/min IP; resend 1/30s, 3/10min, 6/j.
- Implémenter Retry‑After systématique; instrumentation.
- Tests Pytest (ratelimits) + Playwright (429 affichage cooldown).

Dépendances
- Redis opérationnel, paramètres cluster/ACL.

Risques
- Faux positifs en mobilité (IP change), tuning nécessaire.

Critères de fin (DoD S4)
- Tests ratelimits verts; logs/metrics montrent activation; aucune régression UX.

Livrables
- Contrôles de throttling, tests, métriques.

7) Sprint 5 — Gate & Passphrase
Objectifs
- Écrans Gate (absurdité) + passphrase (si prévu produit), transitions d’état cohérentes.
- Intégration complète du tunnel (login→2FA→gate→console).

Tâches
- Vue Gate, stockage passphrase (jamais en clair), politique d’essais/lock.
- Intégration navigation guards, cohérence realms.
- Tests Vitest/Playwright (gate success/failure).

Dépendances
- UX S3; backend si passphrase côté serveur.

Risques
- Complexité flows multi‑étapes; cohérence cookies/realms.

Critères de fin (DoD S5)
- Scénarios E2E Gate verts; logs d’événements complets.

Livrables
- Gate UI/logic, tests, doc UX.

8) Sprint 6 — Observabilité & Alerting
Objectifs
- Events auth:eotp_issued|resent|ok|failed|locked|expired normalisés.
- Métriques clés: latence envoi, taux bounces, taux réussite, échecs par IP/ASN, resend volume.
- Dashboards & alertes (spikes d’échecs, bounces).

Tâches
- Schéma events (labels/fields) + envoi (NATS/HTTP logs).
- Export métriques (Prom/OpenTelemetry) + boards (Grafana/DataDog).
- Alertes: seuils dynamiques (pXX), rate of change; corr_id per event.

Dépendances
- Stack metrics/observabilité disponible.

Risques
- Bruit d’alerting; coûts stockage.

Critères de fin (DoD S6)
- Dashboards opérationnels; alertes testées (dry‑run), documentation d’exploitation.

Livrables
- Events/métriques, dashboards, runbooks.

9) Sprint 7 — Hardening final & DoD global
Objectifs
- Tests unitaires/intégration/E2E “tout vert”, seuils de couverture atteints.
- Rehearsals de rollback/migration; doc finale consolidée.

Tâches
- Revue sécurité (STRIDE), fuzz basique sur endpoints verify/resend.
- Relecture journaux (aucune fuite), validation CSP/reporting.
- Exécution plan de rollback en environnement de stage (simulation).

Critères de fin (DoD S7)
- CI verte (Pytest/Vitest/Playwright); couverture conforme (cf. 05‑test‑strategy.md).
- Checklist DoD globale signée (sécurité, observabilité, perf, UX, docs).

Livrables
- Rapport final, docs à jour, scripts/manuel d’exploitation.

10) Risques transverses et plans de mitigation
- Délivrabilité email (S2): Pré‑checks DNS, sandbox provider, monitoring bounces, fallback SMS non requis (out of scope).
- Entropie/charge Argon2 (S1): Bench & tuning; garde‑fous CPU.
- Mobilité IP (S4): Tolérances UA/IP par flags; logs “low confidence”.
- Endpoints @csrf_exempt historiques: plan d’alignement/compensation via proxy + audit.
- Complexité multi‑realms: matrices cookies/CORS; tests paramétrés.

11) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 06 — Migrations & rollback: ./06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md
- 09 — UX spec: ./09-ux-spec-eotp.md
- 10 — Risques & contingences: ./10-risques-et-contingences.md
