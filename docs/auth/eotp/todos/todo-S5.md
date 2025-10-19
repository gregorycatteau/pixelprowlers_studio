# Todo — Sprint S5 (Gate & Passphrase — intégration tunnel)
Status: DRAFT
Sprint: S5
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 09 — UX spec e‑OTP: ../09-ux-spec-eotp.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif du sprint
- Finaliser le tunnel d’accès après e‑OTP via un “Gate” (écran(s) de contrôle d’accès) et une “passphrase” (si définie côté produit), avec transitions d’état cohérentes jusqu’à /console.
- Garantir une expérience utilisateur claire, auditable et sécurisée (aucune PII en clair, hash des secrets, flags d’activation par realm).

Checklist technique (append‑only)
Backend (Django)
- ⏳ Modèle/stockage passphrase (si requis) — hashée (Argon2id + pepper distincte si sensible) — [02][03]
  Acceptation: aucune passphrase en clair; paramètres de hachage documentés; tests unitaires; migration additive sûre.
  Dép: décision produit sur périmètre passphrase.
- ⏳ Endpoints Gate (ex: POST /api/gate/verify) — [02][03]
  Acceptation: CSRF protect; constant‑time compare; statuts et erreurs uniformes.
  Dép: S1 (auth tunnel) opérationnel.
- ⏳ Transitions d’état tunnel (login → e‑OTP → gate → console) — [02]
  Acceptation: garde serveur cohérente (session/gate_ok); tests d’intégration.
- ⏳ Feature flags par realm (gate_enabled, passphrase_enabled) — [02][06]
  Acceptation: lecture via settings/env; comportement désactivable finement.
- ⏳ Journalisation & events (auth:gate_ok|gate_failed) — [07]
  Acceptation: events PII‑safe; corr_id présent; pas de contenus sensibles.

Front (Nuxt)
- ⏳ Écrans Gate (UI) — [09]
  Acceptation: page dédiée (ex: /gate), champ passphrase (type=password), messages non révélants, a11y (labels, aria‑live).
- ⏳ Navigation/guards — [09][01]
  Acceptation: si gate non validé mais e‑OTP ok → rediriger vers /gate; si gate validé → accès /console; tests e2e.
- ⏳ Mode sombre & responsif — [09]
  Acceptation: styles compatibles dark; confort mobile.

Tests (QA)
- ⏳ Pytest unitaires (backend Gate) — [05]
  Acceptation: hash/verify, CSRF, status, flags; couverture cible ≥ 80% module gate.
- ⏳ Pytest intégration — [05]
  Acceptation: transitions d’état, erreurs uniformes, anti‑rejeu si applicable.
- ⏳ Vitest (composants Gate) — [05][09]
  Acceptation: input passphrase (masquage, validation), messages, a11y; couverture L≥80% sur composants concernés.
- ⏳ Playwright E2E — [05]
  Scénarios:
  - e‑OTP ok → gate → passphrase ok → console
  - e‑OTP ok → gate → passphrase invalide (messages génériques)
  - gate disabled via flag → skip vers console
  Acceptation: verts sans flaky.

Observabilité
- ⏳ Événements: auth:gate_ok|auth:gate_failed (labels realm, decision) — [07]
  Acceptation: events présents; corrélation X‑Request‑ID/Corr_ID.
- ⏳ Métriques: gate_success_total, gate_failed_total, durée gate (issue→ok) — [07]
  Acceptation: visibles en dev/test; histogrammes basiques.

Ops (SRE)
- ⏳ Runbook Gate/Passphrase (support) — [10]
  Acceptation: procédure en cas d’oubli passphrase (si périmètre), ou de taux d’échec anormal; pas d’exposition de secret.
- ⏳ Flags & activation progressive par realm — [06]
  Acceptation: doc d’activation; rollback → flags OFF.

Critères d’acceptation (DoD S5)
- Tunnel complet opérationnel (login→e‑OTP→gate→console) avec flags.
- Aucune fuite de PII/secret; passphrase jamais en clair; comparisons en constant‑time.
- Tests: Pytest (unit/integ), Vitest (UI), Playwright (E2E) verts aux seuils fixés.
- Observabilité: events/métriques de gate actifs et corrélés.

Dépendances
- S1: tunnel e‑OTP livré, endpoints verify/resend.
- S3: écrans e‑OTP; S4: throttling opérationnel.
- Décision produit sur besoin réel de passphrase et périmètre.

Risques spécifiques (S5) & mitigation
- 🔒 Confusion UX (multiplication étapes) — Mitigation: messages clairs; a11y; doc support. Ref: [09][10].
- 🔒 Gestion secrets passphrase — Mitigation: hachage Argon2id + pepper; rotation pepper dans runbook rotate_pepper.md. Ref: [10].
- 🔒 Régressions navigation/guards — Mitigation: E2E exhaustifs; tests de navigation; fallback flags. Ref: [05][10].

Tests & validation — commandes
- Backend:
  - pytest -q -k "gate or passphrase"
- Frontend:
  - cd frontend && npx vitest run --coverage
  - cd frontend && npx playwright test test-e2e/dojo-auth-flow.spec.ts
- Critère “green”: toutes les suites doivent passer; couverture conforme.

Documentation / Appendices
- Mettre à jour: [02] (tunnel final), [07] (events/métriques gate), [09] (écrans Gate), [10] (runbooks).
- Append later: captures anonymisées des dashboards & messages UI.

Notes techniques confirmées à intégrer (rappel)
- Feature flags par realm (gate_enabled, passphrase_enabled).
- Comparaisons constant‑time; logs PII‑safe.
- Runbook rotate_pepper.md à produire pour la pepper passphrase (si différente).

Append‑only
- Ne pas supprimer; append des sous‑tâches/observations datées (journal).
