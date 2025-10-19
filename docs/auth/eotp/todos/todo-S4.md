# Todo — Sprint S4 (Throttling & Résilience — sans Turnstile)
Status: DRAFT
Sprint: S4
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 06 — Plan migrations & rollback: ../06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif du sprint
- Mettre en place le contrôle des abus e‑OTP côté backend (Django/Redis) sans Turnstile: rate‑limits IP/session/utilisateur pour verify/resend, backoff progressif, tarpit contrôlé, Retry‑After systématique, anti‑rejeu strict.
- Consolidation des hooks de sécurité (session/CSRF/cookies) et détection d’anomalies basiques (pistes ASN/IP).
- UX S3 exploite Retry‑After et messages génériques.

Checklist technique (append‑only)
Backend (Django)
- ⏳ Rate‑limit verify (session + IP + user) — [02][03]
  Acceptation: fenêtres par défaut (ex. 6/10min session, 10/min IP), storage Redis (NX/TTL), clés ratelimit:eotp:verify:{scope}:{window}, tests Pytest.
  Dép: Redis opérationnel, S1 endpoints.
- ⏳ Rate‑limit resend (session + user + IP) — [02][03]
  Acceptation: 1/30s, 3/10min, 6/24h; Retry‑After renvoyé; UX lit le header.
- ⏳ Backoff progressif (verify) — [03]
  Acceptation: délai serveur borné (tarpit 100–300 ms au‑delà d’un seuil d’échecs), non bloquant; tests temps simulés.
- ⏳ Retry‑After systématique (429) — [02]
  Acceptation: toutes réponses 429 contiennent Retry‑After (seconds); tests intégration.
- ⏳ Anti‑rejeu strict (vérify/resend) — [03]
  Acceptation: consommation one‑time; resend invalide l’ancien code; tests Pytest.
- ⏳ Contexte UA/IP — tolérance paramétrable par flags — [02][03]
  Acceptation: échec si mismatch en mode strict; logs “low confidence” en mode permissif; tests.
- ⏳ Sécurité session/CSRF/cookies (sanity) — [03]
  Acceptation: tests d’intégration confirment 403 sans CSRF, et cookies ne fuitent pas en logs.

Observabilité
- ⏳ Événements étendus: auth:eotp_failed (motif=rate_limited|invalid|expired), auth:eotp_locked, auth:eotp_resent, auth:eotp_ok — [07]
  Acceptation: events PII‑safe, corr_id présent, request_id propagé.
- ⏳ Métriques: eotp_429_verify_total, eotp_429_resend_total, eotp_locked_total, eotp_success_rate — [07]
  Acceptation: incréments visibles en dev/test; histogrammes latence verify si applicable.
- ⏳ Dashboards: “Sécurité/Abus” (429, locked, heatmap IP/ASN si dispo) — [07]
  Acceptation: panneaux de base; seuils d’alertes alignés.
- ⏳ Alertes:
  - Success rate < 70% → CRIT
  - Locked rate > 10% → CRIT
  - 429 verify spike (abs + variation) → WARN/CRIT — [07]
  Acceptation: règles enregistrées/documentées.

Front (Nuxt) / UX (appui à S3)
- ⏳ Affichage cooldown (Retry‑After) et messages non révélants — [09]
  Acceptation: Playwright “resend cooldown” vert; locked message affiche délai.
- ⏳ Aucune fuite d’état (invalid vs expired) côté UI — [09][03]
  Acceptation: messages génériques testés.

Ops (SRE) / Redis
- ⏳ Paramétrage Redis (ACL/namespace, pool, monitoring latence) — [06][10]
  Acceptation: doc de configuration; métriques latence/erreurs collectées.
- ⏳ Tests de défaillance Redis (grâce/perte) — [10]
  Acceptation: fallback/fail‑closed maîtrisé (définir politique); logs d’alerte.

Critères d’acceptation (DoD S4)
- Rate‑limits verify/resend actifs, testés, avec Retry‑After cohérent; backoff/tarpit opérationnels.
- Anti‑rejeu strict confirmé; contexte UA/IP appliqué selon flags (strict/permissif).
- Playwright: scénarios “429 cooldown” et “locked” verts; UI lit Retry‑After.
- Observabilité: events/métriques/dashboards actifs; alertes enregistrées.
- Logs PII‑safe; aucune fuite de secrets; corrélation request_id assurée.

Dépendances
- S1: endpoints/services en place; flags existants — [04].
- S3: UX lit Retry‑After et affiche correctement messages — [04][09].
- Redis disponible et sain.

Risques spécifiques (S4) & mitigation
- 🔒 Faux positifs en mobilité (rotation IP/CGNAT) — Mitigation: flags permissifs au départ; UA/IP heuristique; surveillance locked_rate. Ref: [10].
- 🔒 Latence excessive (rate‑limit/tarpit) — Mitigation: bornes strictes; métriques p95/p99; ajustements rapides. Ref: [10].
- 🔒 Contournement rate‑limit par IP rotation — Mitigation: combiner scope IP + session + user; heuristique ASN; logs anomalies. Ref: [03][10].

Tests & validation — commandes
- Pytest (backend):
  - pytest -q -k "rate_limit or resend or verify"
- Playwright (frontend):
  - cd frontend && npx playwright test test-e2e/eotp-happy.spec.ts
  - cd frontend && npx playwright test test-e2e/dojo-security.spec.ts -g "rate-limit|429|nonce"
- Critère “green”: toutes les suites passent; 429 inclut Retry‑After; locked et cooldown visibles côté UI.

Documentation / Appendices
- Mettre à jour: [07] (alertes/dashboards), [02] (règles UA/IP), [05] (tests), [10] (risques calibrés/owners).
- Append later: capture anonymisée de dashboards “Sécurité/Abus”, récap des seuils initiaux et des ajustements.

Notes techniques confirmées à intégrer (rappel)
- Redis store pour rate‑limits (clés ratelimit:eotp:*), NX/TTL.
- Retry‑After systématique; messages UI génériques.
- Feature flags par realm pour UA/IP strict/permissif.
- Aucun Turnstile; protections purement serveur.

Append‑only
- Ne pas supprimer; append de sous‑tâches/observations datées (journal).
