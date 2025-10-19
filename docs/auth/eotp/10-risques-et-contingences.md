# 10 — Risques & contingences (registre + plans)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Méthode et périmètre
2. Registre des risques (sécurité, ops, produit)
3. Contingences & runbooks (plans d’action)
4. Déclencheurs d’alerte (seuils, indicateurs)
5. Hypothèses critiques & décisions
6. Dépendances externes & contrats SLO
7. Références internes
8. Points ouverts / TODO

1) Méthode et périmètre
- Périmètre: tunnel e‑OTP (issue/verify/resend), proxies Nuxt, Redis (ratelimits/nonce), email transport/DNS, observabilité, migrations/flags.
- Méthode: classification par catégories (Sécu/OPS/Produit), évaluation “probabilité ~ impact” qualitative, plans de contingence succincts et renvoi vers runbooks.

2) Registre des risques (sécurité, ops, produit)
Sécurité
- R‑SEC‑001 — Brute‑force OTP
  - Cause: tentatives massives de codes 6/8 chiffres.
  - Impact: compromission potentielle si protections insuffisantes; dégradation service.
  - Mitigations: rate‑limits IP/session/utilisateur (Redis), backoff/tarpit, lock après N essais, erreurs uniformes, succès non révélés; tests Pytest/E2E dédiés.
- R‑SEC‑002 — Contournement CSRF / Double‑submit défaillant
  - Cause: absence/rotation du cookie, proxy/middleware mal réglés, Origin/Referer en dev.
  - Impact: requêtes mutatives non autorisées.
  - Mitigations: fetch‑auth (retry contrôlé), /api/auth/csrf proxy robuste; tests E2E 403; ne pas relayer Origin/Referer en dev; revue endpoints @csrf_exempt.
- R‑SEC‑003 — Rejeu de requêtes (nonce)
  - Cause: réutilisation X‑Request‑Nonce.
  - Impact: effets de bord (duplications).
  - Mitigations: RequestNonce Redis NX+TTL; entête X‑New‑Request‑Nonce; tests E2E replay=400.
- R‑SEC‑004 — Mismatch de contexte (UA/IP) et verrouillages faux positifs
  - Cause: mobilité réseau/CGNAT, UA variables.
  - Impact: UX dégradée, support accru.
  - Mitigations: flags eotp_strict_context, heuristique progressive; logs “low confidence”; tolérance initiale puis resserrer.
- R‑SEC‑005 — Fuite de secrets/PII dans logs/Sentry
  - Cause: log inconsidéré de cookies/OTP/emails.
  - Impact: non‑conformité, incident sécurité.
  - Mitigations: redaction PII, beforeSend Sentry, revues de logs; tests de non‑régression grep; interdits documentés.
- R‑SEC‑006 — Session fixation / mauvaise invalidation
  - Cause: flux login→pending_2fa→ok mal séquencé.
  - Impact: élévation de privilèges.
  - Mitigations: rotation session si applicable; vérifications server‑side cohérentes; tests d’intégration.

Opérations (SRE)
- R‑OPS‑001 — Panne Redis (ratelimits/nonce)
  - Impact: protections affaiblies, risques de charge backend.
  - Contingence: fallback cache local (dégradé), baisse quotas automatique, alerte CRIT; communication interne; restauration Redis prioritaire.
- R‑OPS‑002 — Indispo provider e‑mail / Délivrabilité dégradée
  - Impact: OTP non reçus → échec d’auth.
  - Contingence: fallback SMTP sécurisé, circuit‑breaker; alertes sur bounces/spike d’échecs; bascule provider secondaire; runbook “Drop délivrabilité”.
- R‑OPS‑003 — Charge CPU Argon2id mal calibrée
  - Impact: latence verify, saturation workers.
  - Contingence: abaisser paramètres (m/t/p) via config, autoscale; file d’attente; suivi p95/p99; test de charge.
- R‑OPS‑004 — Purge TTL inactive
  - Impact: accumulation eotp_challenge, coût stockage.
  - Contingence: alerte “backlog pending”; activer job purge; exécuter purge manuelle; post‑mortem.
- R‑OPS‑005 — Horloges désalignées (clock skew)
  - Impact: TTL/Retry‑After incohérents.
  - Contingence: NTP vérifié; marges côté serveur; validation en healthcheck.

Produit/UX
- R‑UX‑001 — Frictions fortes (resend/cooldown/timers)
  - Impact: baisse réussite, tickets support.
  - Contingence: ajuster cooldown/profile par flags; améliorer messages; A/B si nécessaire.
- R‑UX‑002 — Accessibilité insuffisante
  - Impact: non‑conformité WCAG, exclusion.
  - Contingence: revue a11y, tests Playwright a11y de base; corrections styling/composants.
- R‑UX‑003 — i18n/wording ambigu
  - Impact: erreurs d’interprétation, phishing facilité.
  - Contingence: revue UX writing; guidelines anti‑phishing; consentement clair.

Conformité & légal
- R‑COM‑001 — Rétention inadéquate
  - Impact: non‑conformité.
  - Contingence: TTL court + purge; pas d’email en clair; minimisation.

3) Contingences & runbooks (plans d’action)
- C‑01 Spike d’échecs verify
  - Déclencheur: success_rate < 70% + failed_total > 3× baseline / 5 min.
  - Actions: vérifier Sentry/proxy_*_failed; baisser eotp_strict_context; inspecter délivrabilité; si attaque → durcir rate‑limits IP; communiquer statut.
- C‑02 Locked rate anormal
  - Déclencheur: locked_rate > 10% / 15 min.
  - Actions: assouplir tolérance UA/IP; relever seuil lock; enquête ASN/IP; dashboard sécurité.
- C‑03 429 verify/resend élevé
  - Déclencheur: > seuil absolu + variation > 200%.
  - Actions: revoir fenêtres; tarpit plus doux; messages UI; notifier Ops.
- C‑04 Provider e‑mail indispo
  - Déclencheur: erreurs API > 5% / 5 min ou statut incident provider.
  - Actions: bascule fallback SMTP; limiter débit; alerter; ouvrir ticket provider.
- C‑05 Redis indispo
  - Déclencheur: latence/erreurs connexions > seuil.
  - Actions: fallback cache; verrouiller certaines actions si nécessaire; alerte CRIT; RTO le plus court.

4) Déclencheurs d’alerte (seuils, indicateurs)
- success_rate < 90% (WARN), < 70% (CRIT) sur 10 min par realm.
- p99(issue→ok) > 10s (WARN), > 15s (CRIT).
- locked_rate > 5% (WARN), 10% (CRIT).
- eotp_429_verify_total/5min > 200 & +200% (WARN).
- hard bounce > 1%/h (WARN), > 3%/h (CRIT) par domaine.
- backlog_pending > N (WARN), > 2N (CRIT).

5) Hypothèses critiques & décisions
- OTP code utilisateur = 6 chiffres (par défaut) — révision possible à 8 via flag.
- Pepper séparée d’APP SECRET_KEY (EOTP_PEPPER) — rotation possible, pepper_id stocké.
- Contexte UA/IP: tolérance initiale; resserrement progressif après observation.
- Endpoint _peek strictement APP_ENV=test (test‑only).

6) Dépendances externes & contrats SLO
- Redis: disponibilité ≥ 99.9% (interne), latence p95 < 5 ms local.
- Provider e‑mail: disponibilité ≥ 99.9%, délai API p95 < 500 ms; engagement DMARC/DKIM pass.
- DNS (SPF/DKIM/DMARC): propagation contrôlée, checks réguliers.
- NATS (optionnel): non bloquant pour auth; QoS défini pour analytics.

7) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 06 — Migrations & rollback: ./06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md
- 09 — UX spec: ./09-ux-spec-eotp.md

8) Points ouverts / TODO
- Calibrer précisément les seuils par environnement (dev/stage/prod).
- Documenter la stratégie de bascule multi‑provider (priorité, drainage).
- Préciser la matrice “probabilité × impact” chiffrée et propriétaires de risques.
- Écrire runbooks détaillés: “Spike failed”, “Redis down”, “Provider down”, “Backlog purge”.
