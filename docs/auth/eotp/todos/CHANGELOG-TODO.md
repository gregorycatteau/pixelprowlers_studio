# CHANGELOG — Todo Lists (S1 → S7)
Status: DRAFT
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17
Version: 0.1

Règles
- Append-only: ne jamais réécrire l’historique, ajouter des entrées datées.
- Statuts utilisables dans les todos: ✅ terminé, ⏳ en cours, 🔒 bloquant/dépendance.
- Portée: suivi des fichiers dans docs/auth/eotp/todos/.

Index
- Tableau de bord: ./index.md
- Todos: ./todo-S1.md … ./todo-S7.md

Journal
2025-10-17 — Initialisation des Todo Lists Sprint e‑OTP (S1 → S7)
- Création: ./index.md (tableau de bord, références S0, règles d’édition)
- Création: ./todo-S1.md (Backend Core e‑OTP)
- Création: ./todo-S2.md (Mailer & Domaine — Postmark, DNS)
- Création: ./todo-S3.md (Front UX e‑OTP — Nuxt)
- Création: ./todo-S4.md (Throttling & Résilience — sans Turnstile)
- Création: ./todo-S5.md (Gate & Passphrase — intégration tunnel)
- Création: ./todo-S6.md (Observabilité & Alerting)
- Création: ./todo-S7.md (Hardening final & DoD)
- Paramètres techniques confirmés intégrés dans les todos (résumé):
  - Backend/Django: Argon2id + pepper (EOTP_PEPPER), calibrage m=64MiB,t=3,p=2, purge Celery beat + VACUUM ANALYZE post‑purge, constant‑time compare, isolation realms.
  - Mail/DNS: Provider Postmark (principal), fallback SMTP TLS, DMARC p=none→quarantine→reject, DKIM 2048 (rotation), bounces webhook (S2).
  - Front/Nuxt: champ OTP unique, timers TTL backend, mode sombre avant S3, Vitest ≥80%, Playwright (happy/invalid/expired/resend/locked).
  - Observabilité: canonical JSON (S6), X‑Request‑ID + Corr_ID, métriques eotp_* et alertes (success<70% CRIT, locked>10% CRIT, hard bounce>3%/h CRIT).
  - Sécurité/SRE: PII‑safe, journal inviolable SHA256(chain), feature flags par realm, runbook rotate_pepper.md à documenter.
- Lien avec Sprint 0: références croisées ajoutées vers 02/03/05/06/07/08/09/10.

À faire (append later)
- Ajouter les Owners par risque dans 10‑risques‑et‑contingences.md et lier depuis chaque todo concerné.
- Ajouter runbook-process.md (cycle alerte → action → ticket → fermeture) et lier depuis S6/S7.
- Journaliser toute mise à jour significative des Todo Lists (ajouts de tâches, changement de statut, décisions d’architecture, seuils métriques).
