# CHANGELOG — Sprint 0 (Préparation méthodologique, sans code métier)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Portée et rappel du cadre
2. Livrables produits (S0)
3. Synthèse cartographie (existant)
4. Écarts vs cible e‑OTP (gap analysis)
5. Décisions prises (S0)
6. Points ouverts (priorisés)
7. Pré‑planification sprints (prêt pour S1)
8. Impacts CI/CD et qualité
9. Sécurité & conformité (rappels S0)
10. Annexes (références)

1) Portée et rappel du cadre
- Sprint 0 strictement documentaire, aucun changement de logique applicative.
- Droit de créer: documents Markdown et éventuels scripts isolés de smoke‑check (non utilisés à ce stade).
- But: fournir architecture cible, threat model, plan d’implémentation et stratégie de tests/observabilité pour lancer S1 immédiatement.

2) Livrables produits (S0)
- 00‑vision‑et‑portee.md — Objectifs, contraintes (sans Turnstile), compatibilité
- 01‑cartographie‑existant.md — Django/Nuxt/Redis/CI, risques initiaux
- 02‑architecture‑cible.md — Modèle eotp_challenge, endpoints, services, flags
- 03‑threat‑model.md — STRIDE, contre‑mesures, plan de tests d’intrusion (S7)
- 04‑plan‑de‑sprints.md — S1→S7, objectifs, périmètre, DoD par sprint
- 05‑test‑strategy.md — Pytest/Vitest/Playwright, critères “green”
- 06‑plan‑migrations‑rollback.md — Migrations DB, activation progressive, rollback
- 07‑observabilite‑alerting.md — Events auth:eotp_*, métriques, dashboards, alertes
- 08‑mail‑transport‑et‑dns.md — Providers, fallback SMTP, SPF/DKIM/DMARC/MTA‑STS/TLSRPT
- 09‑ux‑spec‑eotp.md — Maquettes textuelles, a11y, comportements timers/resend
- 10‑risques‑et‑contingences.md — Registre des risques + plans d’action
État: tous en DRAFT, cohérents et reliés par références croisées.

3) Synthèse cartographie (existant)
- Backend Django:
  - e‑OTP déjà présent (login → pending_2fa, verify/resend, test‑only peek), stockage en cache, hash SHA‑256 + pepper (SECRET_KEY).
  - CSRF double‑submit, RequestNonce (anti‑rejeu) avec Redis, filtres de redaction logs.
- Frontend Nuxt:
  - Proxies SSR robustes (headers/cookies/Retry‑After), composables useAuth/useCsrf/useNonce, plugin fetch‑auth, middlewares auth/realm.
  - E2E Playwright couvrant happy path 2FA (test), CSRF 403 et nonce replay.
- Redis/NATS:
  - Redis disponible (Celery, Nonce/ratelimit possible). NATS optionnel pour events analytics.
Conclusion: base “security‑first” déjà en place, e‑OTP à formaliser côté données/observabilité et durcir côté throttling.

4) Écarts vs cible e‑OTP (gap analysis)
- Données:
  - Manque table eotp_challenge dédiée (audit, statuts, purge TTL, pepper_id, contexte UA/IP).
- Sécurité/résilience:
  - Passer de SHA‑256 à Argon2id + pepper dédiée (EOTP_PEPPER).
  - Durcir throttling (verify/resend) Redis avec quotas et backoff explicites.
- Observabilité:
  - Normaliser events auth:eotp_* + métriques (latence, locked/429, resend).
  - Journal inviolable (chaîne de hachage) à introduire (S6).
- Mail & DNS:
  - Formaliser provider + fallback SMTP, et checklists SPF/DKIM/DMARC/MTA‑STS/TLSRPT.
- UX:
  - Spécifier clairement timers TTL/cooldown, messages uniformes et a11y.

5) Décisions prises (S0)
- Hashing cible: Argon2id + pepper séparée (EOTP_PEPPER), pepper_id stocké en DB.
- Stockage: table eotp_challenge (status pending/consumed/expired/locked), purge TTL planifiée.
- Contexte: lier challenge à session_key + UA hash + IP prefix (/24-v4, /64-v6) avec tolérance contrôlée par flags.
- Resend: invalider le code précédent et régénérer (empêche rejeu).
- Rate‑limit: dimensions IP/session/utilisateur; Retry‑After systématique.
- Observabilité: events standardisés + dashboards + règles d’alerte.
- Activation: progressive via feature flags par realm; Dojo en premier.

6) Points ouverts (priorisés)
P1 (avant S1 freeze)
- Paramètres Argon2id (m/t/p) et note de capacité CPU.
- Choix provider email (Postmark vs SendGrid) + politique DKIM (sélecteurs/rotation).
- Seuils initiaux rate‑limit (verify/resend) par realm; stratégie UA/IP (flags strict/permissif).
P2
- Format canonical_json pour journal inviolable; mécanisme d’ancrage.
- Matrice i18n/UX writing finale, longueur code (6 vs 8).
- CI: service Redis en pipeline vs fakeredis pour tests.

7) Pré‑planification sprints (prêt pour S1)
- S1 livrables: modèle + services issue/verify/resend + endpoints + purge + flags + tests Pytest.
- Dépendances S1: DB/migrations prêtes; pas de blocant identifié.
- S2 et S3 peuvent avancer en parallèle (abstraction mail et UX) avec stubs/mocks en test.

8) Impacts CI/CD et qualité
- Tests:
  - Pytest/Vitest/Playwright déjà configurés; seuils “green” proposés (cf. 05).
- Rapports:
  - JUnit + report HTML Playwright (déjà en place).
- Pipelines:
  - Pas de rupture attendue; ajout de jobs coverage et (option) service Redis.

9) Sécurité & conformité (rappels S0)
- Aucun secret en clair en docs; ne pas exposer OTP/email dans logs/events.
- Endpoint _peek strictement réservé à APP_ENV=test; non exposé prod.
- Redaction PII et protections CSRF/nonce maintenues.

10) Annexes (références)
- Vision: ./00-vision-et-portee.md
- Cartographie: ./01-cartographie-existant.md
- Architecture: ./02-architecture-cible.md
- Threat model: ./03-threat-model.md
- Sprints: ./04-plan-de-sprints.md
- Tests: ./05-test-strategy.md
- Migrations/Rollback: ./06-plan-migrations-rollback.md
- Observabilité: ./07-observabilite-alerting.md
- Mail & DNS: ./08-mail-transport-et-dns.md
- UX: ./09-ux-spec-eotp.md
- Risques: ./10-risques-et-contingences.md
