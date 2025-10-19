# Todo — Sprint S6 (Observabilité & Alerting)
Status: DRAFT
Sprint: S6
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
- Rendre le tunnel e‑OTP pleinement observable et actionnable: événements normalisés (auth:eotp_*), métriques clés, dashboards explicites, règles d’alerting opérationnelles (success rate, locked, 429, bounces), corrélation bout‑en‑bout et journal inviolable par chaîne de hachage.
- Aucun secret/PII en clair dans logs/events; format canonical JSON figé pour S6.

Checklist technique (append‑only)
Backend (Django) — instrumentation
- ⏳ Événements normalisés auth:eotp_* (issued/resent/ok/failed/expired/locked) — [07][02]
  Acceptation: payload PII‑safe (user_id_hash, session_key_hash tronqué, ua_hash, ip_prefix, corr_id, request_id, ttl_sec/tries/resend_count si pertinent); tests Pytest.
- ⏳ Corrélation obligatoire (X‑Request‑ID + Corr_ID) — [07]
  Acceptation: présent sur tous events; propagé depuis Nuxt proxy (SSR) et middleware backend; tests intégration.
- ⏳ Transport events (logs JSON + NATS optionnel) — [07]
  Acceptation: logs JSON conformes; si NATS activé, sujets auth.eotp.* publiés; fallback silencieux si indispo.

Canonical JSON & Journal inviolable
- ⏳ Définir canonical_json(schema v1) — [07]
  Acceptation: ordre/normalisation champs documentés; sérialisation stable; tests de stabilité de hash.
- ⏳ Hash chain (SHA256) — [07]
  Acceptation: H_n = SHA256(H_{n-1} || canonical_json(event_n)); ancrage périodique dans un log/kv immuable; utilitaire de vérification; tests unitaires.
- ⏳ Intégration “no‑secret”: aucun champ sensible; validation grep CI — [07][03]
  Acceptation: tests de non‑régression (aucun code/email/cookie).

Métriques & Dashboards
- ⏳ Métriques eotp_* — [07]
  - eotp_issued_total, eotp_resent_total, eotp_ok_total, eotp_failed_total, eotp_expired_total, eotp_locked_total
  - eotp_429_verify_total, eotp_429_resend_total
  - eotp_issue_to_ok_seconds (histogram)
  Acceptation: endpoints d’export visibles (Prom/Otel); tests Pytest incréments.
- ⏳ Dashboards “Funnel”, “Fiabilité”, “Sécurité/Abus”, “Délivrabilité” — [07]
  Acceptation: panels prêts (templates Grafana/DataDog) avec variables realm; captures anonymisées en annexe.

Alerting
- ⏳ Règles (alignement ref §07) — [07]
  - Success rate < 70% (5‑10 min) → CRIT
  - Locked rate > 10% (15 min) → CRIT
  - 429 verify spike (abs + variation > 200%) → WARN/CRIT
  - Hard bounce > 3%/h (provider/domain) → CRIT
  Acceptation: règles enregistrées; hysteresis/maintenance windows définies; tests de déclenchement en sandbox.
- ⏳ Intégration notifications (canal Ops + ticket auto en CRIT>15m) — [07]
  Acceptation: message formaté avec corr_id, realm, top causes.

Front (Nuxt) — corrélation/PII
- ⏳ Vérifier propagation X‑Request‑ID SSR et absence de cookies/authorization dans Sentry — [01][07]
  Acceptation: tests d’intégration front server; beforeSend Sentry filtrant.

Ops (SRE) & Runbooks
- ⏳ runbook-process.md (cycle alerte → action → ticket → fermeture) — [10]
  Acceptation: documenté (responsables, SLA, escalade); lien depuis index.
- ⏳ Propriétaires des risques (Owner par risque) — [10]
  Acceptation: mise à jour de 10‑risques‑et‑contingences.md avec champ Owner.
- ⏳ Scripts d’audit observabilité (optionnel) — [07]
  Acceptation: script lisant quelques séries/événements pour sanity (dev).

Critères d’acceptation (DoD S6)
- Événements e‑OTP formatés (canonical_json v1), corrélés, sans fuite PII; hash chain en place (vérif offline ok).
- Métriques eotp_* exposées; dashboards opérationnels; règles d’alerting déclenchables et documentées.
- runbook-process.md disponible; risques mis à jour avec Owner.
- Playwright/Pytest non cassés; CI verte.

Dépendances
- S1–S4: endpoints/instrumentations existantes; S2 pour bounces/délivrabilité si activé.
- Stack d’observabilité dispo (Prom/Otel + Grafana/DataDog) ou équivalent.

Risques spécifiques (S6) & mitigation
- 🔒 Bruit d’alerting (fausses alertes) — Mitigation: hysteresis, seuils par environnement, rate‑limit notifications; revue hebdo. Ref: [07][10].
- 🔒 Coût stockage/time series — Mitigation: rétention/aggregation; dashboards concentrés; sampling latence. Ref: [07].
- 🔒 Hash chain perf — Mitigation: bufferiser, batch; vérif offline; pas d’impact chemin critique. Ref: [07].

Tests & validation — commandes
- Pytest (backend):
  - pytest -q -k "events or metrics or hash_chain"
- Audit rapide (script):
  - tools/obs_sanity.sh (append later) — vérifie presence de séries/alerts
- Critère “green”: tests Pytest passent; alertes testées en sandbox; hash chain vérifiée.

Documentation / Appendices
- Mettre à jour: [07] (schéma events, dashboards, alertes), [10] (Owner par risque), [04] (jalons S6).
- Append later: captures anonymisées de dashboards; export JSON rules d’alertes; exemples canonical_json.

Notes techniques confirmées à intégrer (rappel)
- Canonical JSON v1 + SHA256 chain (journal inviolable).
- Corrélation obligatoire X‑Request‑ID + Corr_ID.
- Seuils critiques: success < 70%, locked > 10%, hard bounce > 3%/h.
- PII‑safe partout; Sentry beforeSend supprime cookies/authorization.

Append‑only
- Ne pas supprimer; append des sous‑tâches/observations datées (journal).
