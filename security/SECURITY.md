# Sécurité — PixelProwlers Studio

Ce document définit nos règles de sécurité opérationnelles (“mode chacal 😼”), nos check‑lists par étape, et des bonnes pratiques concrètes pour le frontend (Nuxt 4) et le backend (Django).

Public visé: tous les contributeurs. La sécurité est une responsabilité partagée.


## Sommaire

- Principes et responsabilités
- Gestion des secrets
- Backend (Django) — exigences
- Frontend (Nuxt 4) — exigences
- CI/CD et protections de branches
- Dépendances et chaîne d’approvisionnement
- Journaux, PII et rétention
- Accès, permissions, RBAC
- Modèle de menace “express”
- Check‑lists (PR, Release, Incident)
- Signalement de vulnérabilités


---

## Principes et responsabilités

- Moindre privilège: donner uniquement l’accès nécessaire (personnes, tokens, services).
- Zéro secret en clair: jamais dans le code, les commits, ni les issues/PR.
- Gate partout: lint, type, tests, sécurité (SAST/DAST/deps) bloquent les merges.
- Transparence: incidents et risques documentés vite, sans blame, avec plan d’action.
- Observabilité: logs actionnables sans PII, métriques et alertes sur surfaces critiques.
- Défense en profondeur: validations d’entrées, en-têtes HTTP, CSRF, rate limit, isolation.
- Secure by default: prod verrouillée (HTTPS, cookies sécurisés, erreurs non verbeuses).


## Gestion des secrets

- Stockage:
  - Local dev: fichiers `.env` (non commités). Exemple: `backend/.env`, `.env.dev`, `.env.test`, `.env.prod.local`.
  - CI/CD et prod: Variables d’environnement via le système de secrets de la plateforme (ex: GitHub Secrets).
- Interdits:
  - Pas de secrets en clair dans le repo ni dans les prompts d’IA.
  - Pas de logs contenant des secrets, tokens, clés, PII.
- Détection:
  - Scans secrets automatisés (pré-commit et CI).
- Rotation:
  - Clés/tokens rotatables avec procédure documentée; invalider les anciens artefacts après rotation.
- Nommage et périmètre:
  - Scopes minimalistes; durées de vie courtes si possible (TTL, expiration).


## Backend (Django) — exigences

Paramétrage (via `studio_core.settings.*` et variables d’environnement):
- Bascules prod:
  - `DJANGO_DEBUG=false`
  - `DJANGO_ALLOWED_HOSTS` défini (au strict nécessaire)
  - `SECURE_SSL_REDIRECT=true`
  - `SECURE_HSTS_SECONDS>=31536000` (HSTS), `SECURE_HSTS_INCLUDE_SUBDOMAINS=true`, `SECURE_HSTS_PRELOAD=true`
- Cookies:
  - `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`
  - `SESSION_COOKIE_SAMESITE=Lax` (ou `Strict` selon UX), `CSRF_COOKIE_SAMESITE=Lax`
- En-têtes HTTP:
  - `X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY=same-origin`, `SECURE_CONTENT_TYPE_NOSNIFF=true`
- Auth/JWT:
  - Recommandé RS256: fournir `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` en env
  - Rotation/blacklist activées; lifetimes courts; scopes minimaux
- CSRF/CORS:
  - `CSRF_TRUSTED_ORIGINS` explicite
  - `CORS_ALLOWED_ORIGINS` borné (si CORS activé)
- Rate limiting:
  - Multiples plafonds (`AnonRateThrottle`, `UserRateThrottle`, `ScopedRateThrottle`) configurés
- GraphQL (si utilisé):
  - Profondeur max (`GRAPHQL_MAX_DEPTH`)
  - Operation name requis en prod
  - Rate limit (via `GRAPHQL_RATE`) si `django-ratelimit` disponible
- Admin surface:
  - Faux `/admin/` honeypot (déjà présent) + vrai admin déplacé (`/pp-admin/`)
- DB:
  - `DATABASE_URL` (PostgreSQL) recommandé en prod; SQLite uniquement en dev local
  - SSL client DB en prod si dispo
- Fichiers statiques:
  - WhiteNoise avec manifest (intégrité ressources)
- Erreurs:
  - Messages non verbeux en prod; pas de traces exposées

Entrées, sérialisation, sorties:
- Valider/sanitiser toutes entrées (REST/GraphQL/forms).
- Utiliser l’ORM (évite l’injection SQL); si SQL brut: paramètres liés (`%s`) et contrôle strict.
- Échapper systématiquement les contenus rendus (templates).


## Frontend (Nuxt 4) — exigences

- Secrets:
  - Ne jamais mettre de secrets côté client (utiliser runtime config privée côté serveur).
  - `runtimeConfig.public` uniquement pour données non sensibles.
- En-têtes de sécurité (reverses/proxy/CDN ou Nitro routeRules):
  - CSP stricte (nonce/sha256 pour scripts), `X-Frame-Options: DENY`,
    `Referrer-Policy: strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff`
- Erreurs:
  - Désactiver erreurs verbeuses en prod; pages d’erreur neutres
- XSS/HTML injection:
  - Ne jamais utiliser `v-html` avec des contenus non trustés
  - Échapper/sanitiser données injectées dans le DOM
- Dependencies:
  - Audits réguliers (`npm audit`) + mise à jour proactive (PR bots)
- Build:
  - Budgets de performance: taille de bundle, TTI, hydratation
  - Feature flags pour déploiement progressif


## CI/CD et protections de branches

- Gates CI requis (non contournables):
  - Lint/format: ESLint/Stylelint (front), Ruff (back)
  - Typecheck: `vue-tsc` (front), `mypy` (back) — baseline stricte progressive
  - Tests: unitaires/intégration; min coverage configurable
  - Sécurité:
    - SAST: Bandit (Python) — non bloquant au démarrage, pour devenir bloquant (>medium) ensuite
    - Dépendances: `pip-audit`, `npm audit` — idem (non bloquant au départ)
    - Scan secrets: heuristiques + baseline
- Protections de branches (main):
  - PR obligatoire, min 1 review
  - Checks CI obligatoires (front/back/security)
  - Reviews CODEOWNERS requises (selon la matrice RACI)
  - Dismiss stale approvals si nouveaux commits
  - Conversation resolution obligatoire
  - Pas de bypass des protections
  - Option: commits signés (recommandé)


## Dépendances et chaîne d’approvisionnement

- Verrouillage:
  - Python: `poetry.lock` sous contrôle de version
  - Front: `package-lock.json` (ou `pnpm-lock.yaml` si migration PNPM)
- Mise à jour:
  - Bot (ex: Renovate) pour PR de MAJ régulières
  - Politique d’acceptation: patch/Minor rapide; Major après évaluation
- Revue:
  - Dependency review activée sur PR
- Exécution:
  - Éviter les `postinstall` risqués; audits réguliers
- Conteneurs/Infra (si utilisé):
  - Images pin (tags immuables), scans d’images en CI
  - User non-root, fs read-only si possible, network egress contrôlé


## Journaux, PII et rétention

- Logs:
  - Format structurés; pas de secrets/PII
  - Corrélation requise (Request-ID)
  - Niveaux: INFO en prod; DEBUG interdit côté prod
- PII:
  - Minimiser la collecte; pseudonymiser/agréger si possible
- Rétention:
  - Durées minimales conformes aux obligations; purges planifiées/documentées
- Observabilité:
  - Métriques clés: erreurs (taux/5xx/4xx), latences (p95/p99), saturation
  - Alertes sur SLOs/SLAs


## Accès, permissions, RBAC

- Comptes:
  - 2FA obligatoire pour tous les mainteneurs
  - Clés/jetons personnels rotés et périmés
- RBAC:
  - Rôles par domaine (CODEOWNERS + RACI)
  - Accès prod limités aux ops/autorisés
- Clés d’API:
  - Scope minimal, read-only par défaut
  - Surveiller l’utilisation (métriques, quotas)
- Post-contrat/Offboarding:
  - Révoquer accès et secrets associés immédiatement


## Modèle de menace “express”

- Surfaces:
  - Front: XSS, injection de contenu, dépendances NPM compromises
  - Back: auth/JWT, injections, GraphQL abus (depth/DoS), CORS/CSRF
  - CI: secrets exposés, dépendances compromises, artefacts contaminés
- Scénarios:
  - Compromission de clé JWT → rotation + invalidation refresh + re-déploiement
  - XSS via contenu riche → CSP + sanitisation stricte + bannir v-html
  - Exfiltration via dépendance supply chain → pin + review + SBOM (option)
- Garde-fous:
  - Rate-limit, WAF/CDN, CSP strict, least privilege, attestations CI


## Check‑lists

### A) PR Security Gate

- [ ] Pas de secrets/PII en code, logs, docs, captures
- [ ] Entrées validées/sanitised; aucun `v-html` non sûr (front)
- [ ] Contrôles d’accès/permissions vérifiés (back)
- [ ] En-têtes sécurité adéquats (front/back)
- [ ] Lint/Type/Tests OK; routes critiques couvertes
- [ ] SAST et audits deps passés (bloquants selon politique)
- [ ] Contrats/API documentés; migrations évaluées
- [ ] Observabilité: logs utiles + métriques nécessaires
- [ ] RACI/Owners validés; reviewers sécurité impliqués si sensible

### B) Pre‑Release (environnements supérieurs)

- [ ] `DJANGO_DEBUG=false`, `ALLOWED_HOSTS` défini
- [ ] SSL/TLS OK, HSTS activé, redirection HTTPS
- [ ] Cookies Secure + SameSite, CSRF OK
- [ ] JWT RS256 (clés chargées), rotation testée
- [ ] CSP active et testée (pas de violations bloquantes)
- [ ] DB: migrations appliquées, backup récent
- [ ] Flags de fonctionnalité prêts pour rollout progressif
- [ ] Monitoring/alertes en place; dashboards à jour
- [ ] Plan de rollback documenté et testé

### C) Incident (réponse rapide)

- [ ] Geler l’attaque: désactiver vecteur, couper routes si besoin
- [ ] Rotation secrets/clefs/tokens; invalider sessions/refresh
- [ ] Patcher dépendances vulnérables
- [ ] Vérifier journaux (corrélé, horodaté) et impact
- [ ] Post-mortem sans blame; actions correctives datées
- [ ] Communication interne/externe conforme (si requis)


## Signalement de vulnérabilités

- Contact: security@pixelprowlers.io (ou l’adresse de sécurité officielle de l’organisation)
- Merci d’inclure:
  - Description claire, surface affectée, version/commit, PoC minimal
  - Impact estimé, sévérité, conditions d’exploitation
  - Suggestions de correction ou de mitigation
- Politique:
  - Réponse initiale sous 3 jours ouvrés
  - Suivi et fenêtre de correction proportionnels à la sévérité
  - Reconnaissance des contributeurs responsables (si souhaitée)


---

Garder ce document vivant. Toute amélioration pratique ou durcissement progressif est encouragé — ouvrez une issue “security” et associez les owners pertinents.
