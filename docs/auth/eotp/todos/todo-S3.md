# Todo — Sprint S3 (Front UX e‑OTP — Nuxt)
Status: DRAFT
Sprint: S3
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ../08-mail-transport-et-dns.md
- 09 — UX spec e‑OTP: ../09-ux-spec-eotp.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif du sprint
- Livrer les écrans et comportements UX e‑OTP côté Nuxt: page /login/2fa, champ de saisie OTP (champ unique mobile‑first), timers TTL, bouton resend avec cooldown (lecture Retry‑After), états/erreurs normalisés, a11y.
- Intégration avec composables existants (useAuth, useCsrf, useNonce) et proxies serveur déjà en place.
- Couverture tests: Vitest ≥ 80% sur composants e‑OTP, Playwright scénarios “happy/invalid/expired/resend/locked”.

Checklist technique (append‑only)
Backend awareness (lecture seule)
- ✅ Dépendance S1 endpoints verify/resend disponibles via proxy Nitro — [02][04]
  Acceptation: routes côté frontend pointent sur /server/api/auth/2fa/email/* existants.
- ✅ Dépendance S2 mail non bloquante (peek en test) — [08]
  Acceptation: les E2E utilisent _peek en APP_ENV=test.

Front (Nuxt)
- ⏳ Page /login/2fa (squelette vue) — [09]
  Acceptation: H1 “Vérification à deux facteurs”, texte d’aide; route déclarée; SSR ok.
- ⏳ Champ OTP (champ unique, inputmode=numeric, digits‑only, trim) — [09]
  Acceptation: saisie normalisée; coller autorisé (filtré); maxlength 6/8 via flag eotp_code_length.
- ⏳ Timer TTL (basé uniquement sur valeur backend) — [09][02]
  Acceptation: compte à rebours MM:SS; onExpire déclenche état “expiré” et active resend.
- ⏳ Bouton “Continuer” (submit) avec prévention double‑submit — [09]
  Acceptation: spinner/disabled durant requête; retry contrôlé par plugin fetch‑auth pour CSRF.
- ⏳ Bouton “Renvoyer” (cooldown, lecture Retry‑After) — [09]
  Acceptation: disabled si cooldown actif; affichage compteur; réinitialisation champ OTP après succès resend.
- ⏳ États/erreurs UI (invalid_code, expired, locked, rate_limited) — [09][03]
  Acceptation: messages non révélants; locked affiche délai.
- ⏳ Accessibilité (a11y): labels, aria‑live=polite pour messages, navigation clavier complète — [09]
  Acceptation: revue de base; focus management OK; data‑testid présents (#code, btn-continue, btn-resend, ttl, msg).
- ⏳ Intégration composables (useAuth, useCsrf, useNonce) — [01][09]
  Acceptation: refresh CSRF avant mutatives; cycle de nonce (headers X‑Request‑Nonce / X‑New‑Request‑Nonce) actif via plugin fetch.
- ⏳ Guard de navigation: si déjà authentifié, évite /login/2fa; sinon redirige vers /login si session perdue — [01]
  Acceptation: testé via Playwright (401→/login).
- ⏳ Mode sombre: activer thème Tailwind dark natif pour la vue e‑OTP (pré‑requis S3) — [Paramètre confirmé]
  Acceptation: styles de base compatibles dark; contrastes AA OK.

Tests (QA)
- ⏳ Vitest composants
  - CodeInput: normalisation, coller, auto‑submit optionnel (flag), focus — [05][09]
  - Timer: décompte, onExpire — [05][09]
  - ResendButton: lecture Retry‑After, états disabled/enabled, countdown — [05][09]
  Acceptation: couverture L≥80% sur dossiers composants e‑OTP (istanbul).
- ⏳ Playwright E2E
  - Happy path: login → /login/2fa → peek → verify → /gate — [05]
  - Invalid: code faux → message générique — [05]
  - Expired: attendre TTL 0 → verify échoue → proposer resend — [05]
  - Resend cooldown: 429 → Retry‑After lu → bouton disabled avec countdown — [05]
  - Locked: itérations d’échec → message et délai — [05]
  Acceptation: scénarios verts; sélecteurs robustes (roles/ids), pas de sleep arbitraires.
- ⏳ Tests a11y basiques (Playwright): rôles/labels, navigation clavier — [05][09]
  Acceptation: assertions minimales a11y passent.

Observabilité
- ⏳ Propagation X‑Request‑ID côté Nuxt (middleware SSR existant) — [07]
  Acceptation: en-tête présent/propagé; pas de cookies dans logs.
- ⏳ Logs front sans PII; niveau debug désactivé en prod — [07][03]
  Acceptation: audit grep pass; aucun code/email en clair.

Ops (SRE)
- ⏳ Documentation de configuration front (feature flags e‑OTP consommés côté UI si exposés) — [02][06]
  Acceptation: doc courte ajoutée (fichier notes UI).
- ⏳ Préparation runbook UX (annexes): messages d’erreur usuels et actions support — [10]
  Acceptation: section “Append later” complétée.

Critères d’acceptation (DoD S3)
- Vitest: L≥80% sur composants e‑OTP; tests unitaires verts.
- Playwright: scénarios happy/invalid/expired/resend/locked verts; sélectionneurs robustes.
- A11y: labels, aria‑live, focus management valides sur /login/2fa.
- UI conforme aux règles (champ unique OTP, timers TTL backend, resend cooldown avec Retry‑After).
- Pas de fuite PII; logs front propres; corrélation request_id propagée.

Dépendances
- S1: endpoints verify/resend opérationnels via proxy; flags côté backend — [04].
- S2: non bloquant pour UX; en prod, mail nécessaire (en test, _peek) — [04][08].

Risques spécifiques (S3) & mitigation
- 🔒 Hydration mismatch SSR/SPA — Mitigation: composants “isomorphic” et guards SSR existants; tests visuels; pas de lecture window côté SSR. Ref: [10].
- 🔒 Flakiness E2E (timers) — Mitigation: fake timers en unit, E2E attend URL OU heading; timeouts adaptés (30s). Ref: [05][10].
- 🔒 Erreurs CSRF enchainées — Mitigation: fetch‑auth retry 403→refresh→retry; tests ciblés. Ref: [01][05][10].

Tests & validation — commandes
- Vitest (frontend):
  - cd frontend && npx vitest run --coverage
- Playwright (frontend):
  - cd frontend && npx playwright test test-e2e/eotp-happy.spec.ts
  - cd frontend && npx playwright test test-e2e/dojo-security.spec.ts -g "CSRF|nonce" (sanity)
- Critère “green”: toutes les suites ci‑dessus doivent passer.

Documentation / Appendices
- Mettre à jour: [09] UX spec (captures textuelles finalisées), [05] stratégie de tests (seuils), [07] (notes propagation request_id).
- Append later: ajouter data‑testid aux composants et consigner la liste dans [09]; ajouter exemples d’erreurs affichées (texte exact).

Notes techniques confirmées à intégrer (rappel)
- OTP UI: champ unique (pas 6 cases), inputmode=numeric, mobile‑first.
- Timer TTL: basé uniquement sur valeur backend.
- Mode sombre: défini avant fin S3 (tailwind dark).
- Tests: Vitest ≥ 80%, Playwright scénarios complets.

Append‑only
- Ne pas supprimer les entrées; append des sous‑tâches/observations datées (journal).
