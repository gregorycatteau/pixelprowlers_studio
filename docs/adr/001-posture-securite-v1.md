# ADR 001 — Posture Sécurité v1

- Status: Accepted
- Date: 2025-10-04
- DRI/Owner: @gregorycatteau
- Co-auteurs/Consultés: Bastien (Sécurité), Élodie (CI/CD), Diego (Backend), Chloé/Inès (Frontend)
- Portée: PixelProwlers Studio (monorepo Nuxt 4 + Django)
- Catégorie: Sécurité

## Résumé (one-liner)
Adopter une posture “security by design” v1: en-têtes sécurité via Nuxt/Nitro (CSP report-only puis enforce), JWT RS256 en prod, scans SAST/secret/deps en CI (Bandit gate ≥ medium, pip-audit High/Critical bloquant, Gitleaks non-bloquant puis bloquant), secrets gérés hors repo, logs sans PII.

## Contexte
PixelProwlers Studio vise une “architecture de communication” réplicable et éthique pour petites structures à forte valeur sociale/environnementale. Pour atteindre un standard pro (haut niveau de sécurité, DX robuste, coûts maîtrisés), nous standardisons la posture sécurité dès la v1:
- Front Nuxt 4 + SSR (Nitro)
- Back Django (DRF/GraphQL), JWT
- CI multi-jobs (Web/API/Security)
- CDN contextuel et RAG (vectorisation)

Contraintes:
- Time-to-value court (15 jours)
- Pas d’infra proxy/CDN “ready” tout de suite
- Éviter les régressions UX/SEO
- Maintenir des gates CI réalistes et progressifs

## Enjeux (drivers)
1) Réduction du risque (XSS, CSRF, clickjacking, supply-chain)
2) Exigibilité et traçabilité (gates CI explicites)
3) Evolutivité (politiques reproductibles, infra-agnostiques)
4) Experience dev (DX) et coût de maintenance

## Options considérées (résumé)
- En-têtes sécurité
  - A. Proxy/CDN (source de vérité infra, +latence avant dispo)
  - B. Nuxt/Nitro routeRules (applicables immédiatement) ✅ (retenu)
- Auth
  - A. JWT RS256 en prod, HS256 en dev ✅ (retenu)
  - B. Full session cookies (moins universel pour API publiques)
- Scans sécurité CI
  - A. Bandit gate ≥ medium + pip-audit High/Critical bloquant + Gitleaks non-bloquant→bloquant ✅ (retenu)
  - B. Tout non-bloquant (report-only) (trop faible en v1)

## Décision
- En-têtes sécurité via Nuxt/Nitro:
  - Déploiement immédiat de headers stricts (X-Frame-Options=DENY, X-Content-Type-Options=nosniff, Referrer-Policy=strict-origin-when-cross-origin)
  - CSP en “report-only” pendant 3–5 jours (collecte via `/api/csp-report`), puis passage en “enforce”
  - La même politique sera portée côté proxy/CDN lorsque l’infra sera prête; la source de vérité reste dans le repo
- Auth:
  - Prod: JWT RS256 (clés en ENV/Secrets); Dev/Test: HS256 (fallback ponctuel)
  - Rotation/blacklist activées (SimpleJWT)
- CI sécurité (gates et SLO):
  - Bandit: gate bloquant `≥ medium` (après un cycle de stabilisation)
  - pip-audit: bloquant pour High/Critical dès maintenant; allowlist minimale/justifiée/“datée” si nécessaire (SLO correction: 7–14 jours)
  - Gitleaks: non-bloquant → bascule bloquante après nettoyage des faux positifs éventuels
- Secrets:
  - Jamais dans le repo; via GitHub Secrets/ENV; fichiers `.env*` exclus et exemple `.env.example` fourni
- Logs:
  - Pas de PII, messages actionnables, corrélation par Request-ID

## Conséquences
- Positives:
  - Comportement sécurisé par défaut, reproductible
  - Détection précoce de vulnérabilités (supply chain)
  - Alignement front/back sans dépendre du proxy/CDN
- Négatives/compromis:
  - CSP initialement en report-only (debt temporaire tant que non enforce)
  - pip-audit “strict”: nécessite de traiter certaines updates rapidement
  - Bandit “≥ medium” peut demander des refactors ciblés

## Sécurité & Confidentialité
- Headers:
  - X-Frame-Options=DENY, X-Content-Type-Options=nosniff, Referrer-Policy=strict-origin-when-cross-origin
  - CSP: report-only → enforce, coverage progressive des directives (default-src, script-src, style-src, connect-src, img-src, base-uri, frame-ancestors)
- Auth:
  - RS256 (clé privée/publique), HS256 uniquement dev/test
  - Tokens courts + rotation/blacklist
- Scans:
  - Bandit: `≥ medium` bloquant (après mise à niveau)
  - pip-audit: High/Critical bloquant (allowlist datée si besoin)
  - Gitleaks: non-bloquant puis bloquant
- Logs:
  - No PII; redaction si nécessaire; Request-ID; niveaux ajustés

## Opérations & Fiabilité
- CI:
  - Web: ESLint, Stylelint, Typecheck, Vitest + coverage, npm audit (bloquant High/Critical)
  - API: ruff check/format, mypy (baseline), pytest + coverage, Bandit `≥ medium` (bloquant après adoption), pip-audit (bloquant High/Critical)
  - Security: pip-audit export (Poetry), Gitleaks (non-bloquant→bloquant)
- Enforce CSP:
  - Fenêtre 3–5 jours d’observation; collecter les rapports; nettoyer/ajuster; activer enforce
- Branch protections:
  - PR obligatoire, checks requis, CODEOWNERS review

## Stratégie de tests / QA
- Critères d’acceptation (DoD):
  - Headers renvoyés sur toutes les routes Nitro
  - `/api/csp-report` répond { ok: true }, ne bloque jamais la navigation
  - Bandit report propre ou findings justifiés; gate actif `≥ medium` selon planning
  - pip-audit fail si High/Critical non allowlisté; allowlist datée si présente
  - Gitleaks non-bloquant (passe en bloquant après nettoyage)
  - Tests front/back stables, coverage publié (progression cible: back ≥ 60% en S3)

## RACI (implémentation)
- A (Accountable): @gregorycatteau
- R (Responsible): @gregorycatteau (provisoirement, tant que seul owner)
- C (Consulted): Bastien (Sécurité), Élodie (CI), Diego (Back), Chloé/Inès (Front)
- I (Informed): Jules (Analytics), Farid (Knowledge), Gaëlle (QA)

## Plan d’implémentation (incréments)
- S0 (actuel)
  - Nuxt/Nitro routeRules: headers + CSP report-only + endpoint `/api/csp-report`
  - CI: npm audit High/Critical bloquant; coverage publication; ruff + pytest.ini
  - pip-audit High/Critical bloquant (allowlist datée vide par défaut)
- S1 (durcissement CI)
  - Sortie du “relax mode” CI; ruff check/format; coverage visible
  - Décider/activer Gitleaks bloquant si repo clean
- S2 (sécurité)
  - Bandit gate `≥ medium` bloquant + refactors batch nécessaires
  - CSP “enforce” après 3–5 jours de logs propres
- S3 (qualité produit)
  - Coverage backend ≥ 60%; progression front
  - Observabilité minimale (latence, erreurs)
- Migration proxy/CDN (phase ultérieure)
  - Répliquer la politique CSP/headers côté proxy; garder la source de vérité dans le repo

## Mesure du succès
- CI verte de façon stable; zéros secrets dans les PR
- pip-audit: 0 vuln High/Critical non allowlistée
- Bandit: 0 finding `≥ medium` bloquant en S2
- CSP: logs “propres” puis enforce sans régression
- Temps de remediation (SLO) respecté

## Alternatives non retenues
- “Tout non-bloquant” en sécurité CI: report-only prolongé
  - Rejeté: risque trop élevé, manque d’effet utile
- CSP directement en enforce sans période d’observation
  - Rejeté: casse potentielle sans visibilité préalable

## Questions ouvertes
- Périmètre exact des directives CSP à “assouplir” selon intégrations futures (fonts, analytics sous flag)
- Politique de secrets scanning bloquante (Gitleaks) — date cible d’activation

## Références
- CI workflows (Web/API/Security)
- SECURITY.md (compléter: rotate secrets, runbook incidents)
- Roadmap 15 jours
- Nuxt Nitro routeRules documentation
- pip-audit, Bandit, Gitleaks

---

Meta
- Supersedes: N/A
- Superseded by: N/A (révision possible lors de la mise en place proxy/CDN)
- Changelog:
  - 2025-10-04: Accepted (posture v1; CSP report-only → enforce; JWT RS256 prod; Bandit `≥ medium`; pip-audit High/Critical; Gitleaks non-bloquant→bloquant)
