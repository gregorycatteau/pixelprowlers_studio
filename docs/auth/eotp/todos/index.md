# e‑OTP — Tableau de bord des Todo Lists (S1 → S7)
Status: DRAFT
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17
Version: 0.1

Références Sprint 0
- 00 — Vision et portée: ../00-vision-et-portee.md
- 01 — Cartographie de l’existant: ../01-cartographie-existant.md
- 02 — Architecture cible: ../02-architecture-cible.md
- 03 — Threat model: ../03-threat-model.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 06 — Plan migrations & rollback: ../06-plan-migrations-rollback.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ../08-mail-transport-et-dns.md
- 09 — UX spec e‑OTP: ../09-ux-spec-eotp.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif
- Centraliser la progression des sprints (S1 → S7) via des Todo Lists append‑only.
- Chaque todo est autoportant, modulaire, et référencé depuis ce tableau de bord.
- Aucun code applicatif n’est modifié dans cette phase.

Liens vers les Todo Lists par sprint
- S1 — Backend Core e‑OTP: ./todo-S1.md
- S2 — Mailer & Domaine: ./todo-S2.md
- S3 — Front UX e‑OTP (Nuxt): ./todo-S3.md
- S4 — Throttling & Résilience: ./todo-S4.md
- S5 — Gate & Passphrase: ./todo-S5.md
- S6 — Observabilité & Alerting: ./todo-S6.md
- S7 — Hardening final & DoD: ./todo-S7.md

Progression globale (initialisation)
- S1: 0% (0/0) — initialisation en attente
- S2: 0% (0/0) — initialisation en attente
- S3: 0% (0/0) — initialisation en attente
- S4: 0% (0/0) — initialisation en attente
- S5: 0% (0/0) — initialisation en attente
- S6: 0% (0/0) — initialisation en attente
- S7: 0% (0/0) — initialisation en attente

Règles d’édition
- Append‑only: ajouter de nouvelles entrées, ne pas supprimer l’historique.
- Statuts de tâches:
  - ✅ terminé
  - ⏳ en cours
  - 🔒 bloquant/dépendance
- Chaque Todo liste son DoD (critères de fin), ses tests (Pytest/Vitest/Playwright), ses risques, et références Sprint 0.
- Les dépendances inter‑sprints doivent être indiquées pour chaque tâche concernée.

Journal des changements (Todo)
- Voir: ../CHANGELOG-TODO.md

Notes techniques à intégrer dans les Todos (rappel)
- Backend/Django: Argon2id + pepper (EOTP_PEPPER), calibrage (m=64 MiB, t=3, p=2), Celery beat pour purge TTL, VACUUM ANALYZE post‑purge, constant‑time compare, isolation par realm.
- Mail & DNS: Provider Postmark, fallback SMTP TLS, DMARC p=none→quarantine→reject, DKIM 2048/rotation, webhooks bounces (S2).
- Front/Nuxt: champ unique OTP, inputmode=numeric, timers basés sur backend, mode sombre (avant S3), Vitest ≥80%, Playwright scénarios (happy/invalid/expired/resend/locked).
- Observabilité: canonical JSON (S6), X‑Request‑ID+Corr_ID obligatoires, métriques eotp_* et alertes (success<70%, locked>10%, hard bounce>3%/h).
- Sécurité/SRE: PII‑safe logs, journal inviolable SHA256(chain), feature flags par realm, runbook rotate_pepper.md à prévoir.
