# CHANGELOG — Rapport final e‑OTP (pré‑S1)
Status: DRAFT
Auteur: Cline (Chef d’intégration technique & SRE auditeur)
Date: 2025-10-17
Version: 1.0

Objet
- Journal append‑only des évolutions liées au rapport consolidé pré‑S1 et de la préparation d’exécution (sans code métier).

Entrées
2025-10-17 — Création du rapport consolidé et alignement final
- Ajout: docs/auth/eotp/rapport-final-eotp.md (blueprint définitif, pré‑S1)
  - Inclus “🧱 Blocs de validation” par section (Acquis / En cours / À faire)
  - État de conformité par sprint (S1→S7) + tableau récapitulatif (points forts, ajustements)
  - Recommandations obligatoires et plan de durcissement avant exécution
  - Annexes (Owners → risques, Canonical JSON v1 & hash chain, outils /tools/, références croisées)
- Paramètres de config à figer (à documenter dans backend/README.md + backend/.env.dev)
  - EOTP_TTL=300; MAX_TRIES=3; COOLDOWN_SECONDS=30; EOTP_PEPPER=(secret env); HASH_CHAIN_ALGO=SHA256; ARGON2_M=64MiB; ARGON2_T=3; ARGON2_P=2
- Outils internes planifiés (référencés dans le rapport, à créer en phase d’implémentation)
  - tools/test_backoff.sh — simulateur de spam verify/resend (observe 429 / Retry‑After / locked)
  - tools/verify_log_chain.py — vérification d’intégrité de la chaîne de hachage (canonical_json v1)
  - tools/obs_sanity.sh — sanity observabilité (métriques eotp_* + alert rules)
- Runbooks à ajouter (statut DRAFT, requis avant fin S1)
  - docs/auth/eotp/runbooks/runbook-process.md — cycle alerte → action → ticket → fermeture
  - docs/auth/eotp/runbooks/rotate_pepper.md — procédure de rotation pepper (+ post‑checks)
  - docs/auth/eotp/runbooks/celery-beat-purge.md — diagnostic purge TTL / backlog / VACUUM
- Ajustements techniques intégrés dans le plan (et répercutés dans les Todos)
  - S1: supprimer UNIQUE(session_key,status='pending'); introduire device_hash optionnel (activation S3)
  - S2: vérification mensuelle de la rotation DKIM (cron/check DNS)
  - S3: fallback offline sans JS (“code expiré / pas reçu ?”)
  - S4: simulateur interne d’abus pour tester throttling
  - S5: trancher passphrase statique (rotation) vs contextuelle; documenter TTL
  - S6: test test_canonical_json_deterministic_hash()
  - S7: scans SBoM (pip‑audit, npm audit) + CLI verify_log_chain.py
- Interopérabilité S1 ↔ S6 (confirmée)
  - Les événements auth:eotp_* (issued/resent/ok/failed/expired/locked) de S1 alimentent directement les métriques et alertes S6; schéma canonical_json v1 figé en annexe
- Pré‑S1 — vérifications à exécuter (sans code)
  - DB: dry‑run migrations (makemigrations --check)
  - Argon2id: latence issue/verify + CPU (p50/p95/p99) → calibrage m/t/p si besoin
  - Sécurité: pip‑audit, bandit, safety; npm audit (front)
  - Celery: “eotp_purge_expired” visible (celery inspect scheduled)
- Aucune modification de code métier; CI/CD non impactée (docs only)

2025-10-17 — Addenda (stabilisations S1 + fondations S3)
- S1 stabilisations (réalisé):
  - Route test pour webhook Postmark exposée (backend/studio_core/test_urls_eotp.py → /api/webhooks/postmark/bounce/) + tests signature OK/KO verts.
  - Test quota resend déterministe: neutralisation du cooldown session et patch de constante à l’import pour vérifier 3/h (verts).
  - Flag EOTP_DISABLE_HMAC_FALLBACK ajouté (désactive fallback SHA‑256 en prod) + .env.example mis à jour (MAILER_PROVIDER/POSTMARK_*).
  - Documentation DNS Postmark ajoutée (docs/auth/eotp/dns/POSTMARK_DNS.md — SPF, DKIM 2048, Return‑Path, DMARC, MTA‑STS, TLSRPT).
- S3 fondations (réalisé partiel):
  - Activation Pinia (@pinia/nuxt).
  - Store e‑OTP (frontend/app/stores/useEotpStore.ts) avec TTL/cooldowns, actions verify/resend/fetchPeek et respect strict Retry‑After.
  - Tests unitaires Vitest verts (7/7) avec jsdom + shim #imports (frontend/vitest.config.ts, frontend/test/shims/nuxt-imports.ts).
  - Incident npm EACCES front résolu: reset node_modules (création node_modules.old_*), à purger ultérieurement.

Liens
- Rapport: ./rapport-final-eotp.md
- Todos (tableau de bord): ./todos/index.md
- Todos Sprints: ./todos/todo-S1.md … ./todos/todo-S7.md
- CHANGELOG Sprints: ./CHANGELOG-S1.md, ./CHANGELOG-S3.md
- CHANGELOG Todos: ./todos/CHANGELOG-TODO.md

Notes
- Le hash SHA256 du corpus documentaire sera ajouté en Annexe E du rapport lors du tag “v0-sprint0bis”.
