# 06 — Plan de migrations & rollback (e‑OTP)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Objectifs et principes SRE
2. Périmètre des changements (DB / flags / jobs)
3. Migrations de schéma (PostgreSQL)
4. Activation progressive (feature flags)
5. Plan de rollback (schéma, données, applicatif)
6. Orchestration du déploiement (0‑downtime)
7. Données: rétention, purge TTL, conformité
8. Vérifications post‑déploiement (smoke & health)
9. Outils & scripts opératoires
10. Risques & mitigations
11. Références
12. Points ouverts / TODO

1) Objectifs et principes SRE
- Introduire e‑OTP de façon sécurisée, réversible et observable.
- Zéro interruption pour le trafic existant (0‑downtime).
- Activation progressive via feature flags (realm/segment).
- Pas de fuite de secrets; logs et métriques en place dès S1.
- Rollback simple et documenté (jusqu’au niveau DB si besoin).

2) Périmètre des changements (DB / flags / jobs)
- Base de données (nouveau schéma):
  - Table eotp_challenge (cf. 02‑architecture‑cible.md).
  - Index de performances/purge.
- Feature flags (config/app):
  - eotp_enabled, eotp_code_length, eotp_strict_context, eotp_cooldown_profile.
- Jobs planifiés:
  - Purge TTL (management command + Celery beat/cron).
- Aucune suppression/modification d’objets existants en Sprint 1 (additive only).

3) Migrations de schéma (PostgreSQL)
3.1. Table eotp_challenge (nouvelle)
- Colonnes clés
  - id uuid PK (DEFAULT gen_random_uuid()).
  - user_id FK → auth_user (NULLABLE si flux “email‑first” futur).
  - session_key varchar(64) NOT NULL (INDEX).
  - status enum('pending','consumed','expired','locked') NOT NULL DEFAULT 'pending'.
  - code_hash text NOT NULL (Argon2id).
  - algo varchar(16) NOT NULL DEFAULT 'argon2id'.
  - pepper_id varchar(32) NOT NULL.
  - tries_count int NOT NULL DEFAULT 0.
  - resend_count int NOT NULL DEFAULT 0.
  - created_at timestamptz NOT NULL DEFAULT now().
  - expires_at timestamptz NOT NULL.
  - last_sent_at timestamptz NULL.
  - context_ua char(56) NULL.
  - context_ip_prefix varchar(64) NULL.
  - corr_id varchar(64) NULL.
- Index proposés
  - idx_eotp_session_key (session_key).
  - idx_eotp_status_expires (status, expires_at).
  - idx_eotp_user_created (user_id, created_at DESC).
  - idx_eotp_created (created_at).
- Contraintes
  - CHECK (expires_at > created_at).
  - Optional: UNIQUE(session_key, status) WHERE status = 'pending' (empêcher plusieurs pending concurrents par session).
- Notes de compatibilité
  - Migration purement additive (pas d’impact sur chemins existants).
  - Pas de données à backfiller.

3.2. Enum status (option d’implémentation)
- Soit un type enum SQL; soit un varchar(16) + CHECK pour limiter les risques lors d’évolutions.
- Recommandation: varchar(16) + CHECK (agile pour itérer durant S1–S4).

3.3. Sécurité & perfs
- Taille code_hash: Argon2id encodé base64 → text OK.
- Expliquer paramètres Argon2id (m/t/p) dans la doc d’exploitation.
- Index “status,expires_at” pour purge performante.

4) Activation progressive (feature flags)
4.1. Flags et stratégies
- eotp_enabled (bool/percent/segment) par realm:
  - Phase 1: OFF partout.
  - Phase 2: ON pour realm Dojo (admin).
  - Phase 3: Gradation progressive sur Clients.
- eotp_strict_context (UA/IP):
  - Démarrer permissif (taux d’échec observé) → resserrer progressivement.
- eotp_code_length (6 → 8) — décider après métriques initiales.
- eotp_cooldown_profile: profils de cooldown/resend (A/B possible).

4.2. Séquence d’activation
- Étape 0: Déploiement migrations + code dormant (flags OFF).
- Étape 1: Activer eotp_enabled pour Dojo en “shadow” (logs/metrics, peu d’utilisateurs).
- Étape 2: Ajuster thresholds (rate‑limit, cooldown), confirmer stabilité (SLO).
- Étape 3: Étendre à Clients (batchs), surveiller KPIs (taux ok/failed/locked/bounces).
- Étape 4: Basculer flags stricts si KPIs OK.

5) Plan de rollback (schéma, données, applicatif)
5.1. Rollback applicatif (préféré)
- Désactiver eotp_enabled (flags → OFF) pour revenir au comportement pré‑e‑OTP (les endpoints existants hors e‑OTP restent opérationnels).
- Laisser la table eotp_challenge en place (additive, sans impact).

5.2. Rollback de configuration
- Revenir aux profils de cooldown antérieurs, assouplir eotp_strict_context si faux positifs.

5.3. Rollback schéma (rarement nécessaire)
- Étape 1 (option): arrêter purge job pour congeler l’état.
- Étape 2: DROP INDEX … puis DROP TABLE eotp_challenge (uniquement si exigence légale/technique).
- Important: cette étape nécessite une fenêtre de maintenance dédiée; à éviter si possible (préférer inertie du schéma + flags).

6) Orchestration du déploiement (0‑downtime)
6.1. Ordonnancement recommandé
- Phase A (maintenance préparatoire — sans interruption):
  - Appliquer migrations DB.
  - Déployer code serveur qui lit flags (comportement backward‑compatible).
  - Déployer job de purge (désactivé par défaut, flag/cron OFF).
- Phase B (post‑déploiement):
  - Activer job de purge (cron/Celery beat).
  - Allumer eotp_enabled sur un segment restreint (Dojo).
  - Effectuer smoke tests (voir §8).
- Phase C (élargissement):
  - Étendre flags si KPIs et logs/sentry verts.

6.2. Compatibilité versionnée
- Toutes les versions “n+1” doivent tolérer la présence de la table même si non utilisée.
- Les endpoints verify/resend doivent retourner des erreurs uniformes si flag OFF (ne pas “leaker” d’état).

7) Données: rétention, purge TTL, conformité
- Rétention éOTP:
  - TTL court via expires_at (ex. 3–5 min).
  - Purge régulière: DELETE WHERE expires_at < now() OR (status IN (consumed, locked) AND created_at < now()-N minutes).
- Conformité/PII:
  - Aucune adresse email en clair dans eotp_challenge.
  - user_id présent seulement si nécessaire.
  - code_hash irréversible; pepper_id stocké, pas la pepper.
- Sauvegardes:
  - Les lignes e‑OTP sont éphémères (peu d’intérêt aux backups); vérifier politiques de rétention bases complètes.

8) Vérifications post‑déploiement (smoke & health)
- Smoke backend (Pytest ciblé ou scripts tools/):
  - Création challenge via login pending_2fa (realm Dojo), observe INSERT en DB.
  - Verify OK avec code de test (APP_ENV=test via _peek).
  - Resend → 429 + Retry‑After respecté.
- Smoke frontend (Playwright):
  - eotp-happy.spec.ts (déjà présent).
  - dojo-security.spec.ts (403 CSRF, nonce replay).
- Observabilité:
  - Metrics eotp_* non nulles et cohérentes (issued/ok/failed/resent/locked/expired).
  - Aucun secret dans logs/Sentry (sanity via grep/CI).

9) Outils & scripts opératoires
- Management command (Django):
  - manage.py eotp_purge_expired — exécutable manuellement et par planification.
  - manage.py eotp_stats — count par status/realm (optionnel pour S6).
- tools/ (facultatif, Sprint 0 autorisé):
  - scripts de smoke: HTTP simple (login→2fa→verify) en mode test; NE PAS inclure secrets.
  - script de vérification Retry‑After (resend).

10) Risques & mitigations
- Charge CPU Argon2id:
  - Mitigation: paramètres calibrés; mesurer p50/p95; autoscaler/worker tuning.
- Faux positifs contexte UA/IP:
  - Mitigation: eotp_strict_context OFF au début; logs “low confidence”.
- Délivrabilité email:
  - Mitigation: S2 (DNS, bounces); en test, endpoint _peek évite la dépendance transport.
- Accumulation en DB (purge inactive):
  - Mitigation: alerte sur “pending > seuil”, dashboards; job purge ON par défaut après validation.
- Régression CSRF/nonce:
  - Mitigation: suites E2E existantes + nouveaux cas e‑OTP.

11) Références
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md

12) Points ouverts / TODO
- Décider UNIQUE(session_key,status='pending') vs multi‑pending (cas multi‑device).
- Finaliser paramètres Argon2id (m/t/p) cibles & note de calcul capacité.
- Choisir mécanisme d’ordonnancement purge (Celery beat vs cron k8s).
- Rédiger runbook d’incident “spike failed/429/locked” (seuils, actions).
- Documenter procédure d’activation par batch côté Clients (échantillonnage).
