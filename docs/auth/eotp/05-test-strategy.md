# 05 — Stratégie de tests (Pytest / Vitest / Playwright / CI)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Objectifs et périmètre
2. Pyramide de tests et critères “green”
3. Backend (Pytest) — plan détaillé
4. Frontend (Vitest) — plan détaillé
5. E2E (Playwright) — scénarios et stabilité
6. Données de test, fixtures, mocks (mail/Redis)
7. Intégration CI (rapports, seuils, parallélisme)
8. Anti‑flakiness et performance
9. Sécurité: tests ciblés (CSRF, nonce, rate‑limit, anti‑rejeu)
10. Observabilité: vérifications d’events/métriques
11. Références internes
12. Points ouverts / TODO

1) Objectifs et périmètre
- Garantir la qualité fonctionnelle et la sécurité du tunnel e‑OTP (issue/verify/resend, TTL, statuts).
- Assurer la compatibilité avec l’écosystème actuel: Django + Nuxt, proxies SSR, CSRF double‑submit, Request‑Nonce.
- Définir des critères “green” concrets (seuils couverture, temps d’exécution, stabilité) pour la CI.
- Préparer les fondations pour les sprints d’implémentation 1→7.

2) Pyramide de tests et critères “green”
- Pyramide:
  - Unitaires (rapides): services e‑OTP, helpers, formatage, stores/front composables.
  - Intégration: endpoints Django (CSRF, sessions, rate‑limit Redis), proxies Nitro, enchaînements front (sans navigateur).
  - E2E (navigateur): flux complets login→2FA→gate, erreurs (invalid/expired/resend/429).
- Critères “green”:
  - Couverture minimale (ligne/branches):
    - Backend module e‑OTP: L: ≥ 85%, B: ≥ 75%
    - Front e‑OTP (composants/stores): L: ≥ 80%, B: ≥ 70%
  - Durée CI:
    - Pytest ≤ 6 min, Vitest ≤ 2 min, Playwright (smoke + e‑OTP) ≤ 10 min sur agents standard.
  - Stabilité:
    - Flaky rate ≤ 1% (ré‑essai ×1 max pour E2E critiques).
  - Rapports:
    - JUnit XML publiés; HTML Playwright archivé.
  - Qualité sécurité:
    - Tests CSRF et nonce replay strictement verts; rate‑limits effectives (429 + Retry‑After).

3) Backend (Pytest) — plan détaillé
- Portée:
  - Modèle eotp_challenge (migrations, index, contraintes).
  - Services: issue(), verify(), resend()
    - issue: secret 128 bits, code 6/8 chiffres, Argon2id + pepper, TTL, status=pending.
    - verify: constant‑time compare, transitions → consumed, anti‑rejeu, tries_count, lock.
    - resend: quotas + cooldown, invalider ancien code, regénérer, Retry‑After.
  - Contexte: liaison session_key, UA hash, IP prefix.
  - Purge TTL (management command): supprime expired/consumed/locked anciens.
  - CSRF: endpoints verify/resend protégés (403 si header manquant/mauvais).
  - Rate‑limit: verify/resend (par session, user, IP) avec Redis (ou fallback cache en dev).
  - Journalisation & events: record_auth_event(eotp_*), pas de secret en clair.
- Fixtures:
  - db (transactionnel), settings (EOTP_PEPPER, TTL), client DRF/CSRF.
  - redis_stub (fakeredis ou backend cache Redis si accessible).
  - mail_outbox stub (backend EmailBackend in‑memory).
- Cas de tests (exemples):
  - test_issue_cree_challenge_pending_avec_hash_argon2id
  - test_verify_code_valide_change_status_en_consumed_et_bloque_rejeu
  - test_verify_code_invalide_incremente_tries_et_applique_backoff
  - test_resend_applique_cooldown_et_quota_et_regenere_code
  - test_verify_mismatch_contexte_ua_ip_echec_selon_flag
  - test_purge_supprime_expired_et_anciens_consumed_locked
  - test_csrf_obligatoire_sur_verify_resend_403
  - test_rate_limit_verify_resend_retourne_429_avec_retry_after
  - test_events_emis_sans_exposer_code_ou_email
- Couverture:
  - coverage.py activé, rapport XML pour CI, seuils enforce.

4) Frontend (Vitest) — plan détaillé
- Portée:
  - Composants e‑OTP:
    - CodeInput: normalisation (digits‑only, trim), focus/aria, paste.
    - Timer: décompte TTL (MM:SS), formatage, arrêt à 0.
    - ResendButton: états disabled/enabled selon cooldown, lecture Retry‑After.
    - Login2FAView: rendu heading, champs #code, messages d’erreur normalisés.
  - Stores/Composables:
    - useAuth: login→pending_2fa, fetchMe hydration, logout (reset + csrf.refresh()).
    - useCsrf: refresh(), stockage token, erreur 403→retry controlé.
    - useNonce: cycle X‑New‑Request‑Nonce, clear().
  - Plugin fetch‑auth:
    - Ajout auto X‑CSRFToken pour mutatives; ajout X‑Request‑Nonce sur /api/(gates|agents|conversations|messages)
    - 401→reset + redirect /login; 403 csrf_failed→retry 1 fois.
- Mocks:
  - $fetch client (interception), headers/Retry‑After simulés.
  - GlobalThis timers (fake): vitest.useFakeTimers().
- Cas tests (exemples):
  - code_input_normalise_et_emet_evenement_submit_sur_longueur_ok
  - timer_compte_à_rebours_et_declenche_onExpire
  - resend_button_respecte_retry_after_et_affiche_compte_à_rebours
  - fetch_auth_reinjecte_csrf_et_retry_sur_csrf_failed_puis_abort
- Couverture:
  - vitest --coverage (istanbul) avec seuils L/B définis ci‑dessus.

5) E2E (Playwright) — scénarios et stabilité
- Base:
  - playwright.config.ts (reports list+junit+html, projects browsers).
  - docker-compose.playwright.yml disponible (exécution headless en conteneur).
- Scénarios:
  - Happy path (déjà présent): login→/login/2fa→peek (APP_ENV=test)→verify→/gate.
  - Invalid code: message générique, compteur tentatives, pas d’indice d’état.
  - Expired: après TTL, verify échoue → UI propose resend.
  - Resend cooldown/quota: 429 + Retry‑After; bouton disabled avec countdown.
  - CSRF manquant: 403 (déjà couvert dans dojo‑security.spec.ts).
  - Nonce replay: rejet 400 nonce_replay (déjà couvert).
  - Logout: retourne /login et nettoie états.
- Stabilité:
  - Attendre URL OU heading visible (race‑safe SSR/SPA).
  - Locators précis (role, testId éventuel), pas de sleep arbitraire (waitForResponse/URL).
  - Retry ciblé (1x) pour scénarios sensibles au timing réseau.

6) Données de test, fixtures, mocks (mail/Redis)
- Backend:
  - APP_ENV=test: activer endpoint _peek sécurisé pour OTP (uniquement test).
  - DB éphémère (sqlite3 en test ou Postgres locale) + migrations auto.
  - Redis: fakeredis ou instance locale isolée (database id).
- Frontend:
  - E2E_USER/E2E_PASS fournis via env pour Playwright.
  - Base URLs:
    - PPW_BASE_URL (Nuxt), DJANGO_BASE_URL (backend) cohérents en local.
  - Mail:
    - Stub provider en test; pas d’envoi réel (sprint 2 doc/impl).

7) Intégration CI (rapports, seuils, parallélisme)
- Jobs:
  - pytest: coverage + junit (backend)
  - vitest: coverage + junit (frontend)
  - playwright: junit + html report (artifact)
- Parallélisme:
  - Séparer jobs backend/frontend; E2E après build & dev servers up (ou via docker‑compose.*).
- Rapports:
  - frontend/reports/e2e.xml (déjà configuré)
  - Artifacts: playwright-report/ archivé.
- Gates:
  - Enforce seuils de couverture (fail si < seuil).
  - Marquer flaky tests (tag @flaky) avec retry unique; alerte si count > N.

8) Anti‑flakiness et performance
- Vitest: fake timers, mocks réseau, tests isolés sans dépendance SSR.
- Playwright:
  - waitForURL OR heading visible (race SSR/SPA).
  - Réduire dépendance à animations; augmenter timeouts sur étapes réseau critiques (30s déjà utilisé).
  - Utiliser test.describe.serial uniquement si nécessaire (nonce replay).
- Performance smoke:
  - Mesurer temps issue→verify (p50/p95) en test; seuil d’alerte documentaire (observabilité Sprint 6).

9) Sécurité: tests ciblés (CSRF, nonce, rate‑limit, anti‑rejeu)
- CSRF:
  - POST verify/resend sans header → 403.
- Nonce:
  - Rejeu d’un même X‑Request‑Nonce sur endpoints sensibles → 400 nonce_replay.
- Rate‑limit:
  - Dépasser fenêtres verify/resend → 429 + Retry‑After; UI affiche countdown.
- Anti‑rejeu e‑OTP:
  - Réutiliser code après succès → invalid_code uniforme (aucune fuite d’état).
- Contexte:
  - Mismatch UA/IP selon flags → échec attendu (et log “low confidence”).

10) Observabilité: vérifications d’events/métriques
- Events:
  - auth:eotp_issued|resent|ok|failed|expired|locked émis aux moments clés.
  - Corrélation: X‑Request‑ID présent; corr_id dans payload event (si applicable).
- Métriques:
  - Compteurs par decision; latence issue→ok; volume resend; taux d’échec par IP/ASN.
- Non‑régression:
  - Tests peuvent stubber le collecteur (NATS/HTTP) et valider un échantillon d’événements.

11) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 06 — Migrations & rollback: ./06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md
- 09 — UX spec: ./09-ux-spec-eotp.md

12) Points ouverts / TODO
- Fixer précisément les seuils coverage “green” globaux du repo (monorepo vs packages).
- Choisir la stratégie Redis en CI (fakeredis vs service docker).
- Définir un minimal set E2E “smoke” pour PR rapides, et une suite “complète” en nightly.
- Décider d’un process automatique de quarantine des tests flakys avec ticketing.
