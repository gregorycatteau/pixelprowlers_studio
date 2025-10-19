# 07 — Observabilité & alerting (e‑OTP)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Objectifs et principes
2. Événements “auth:eotp_*” (contrat)
3. Transport et corrélation (logs, NATS, X‑Request‑ID)
4. Métriques clés (définitions)
5. Tableaux de bord (dashboards)
6. Alerting (seuils, règles, suppressions)
7. Journal inviolable (chaîne de hachage)
8. Points d’instrumentation (Django/Nuxt)
9. SLO/SLA & revue opérationnelle
10. Confidentialité & redaction PII
11. Références internes
12. Points ouverts / TODO

1) Objectifs et principes
- Rendre le tunnel e‑OTP observable (issue → verify → ok/failed/expired/locked/resent).
- Suivre fiabilité, sécurité et délivrabilité (sans fuite de secrets).
- Alerter rapidement sur incidents (spikes d’échecs, 429, bounces) avec bruit maîtrisé.
- Corréler bout‑en‑bout via X‑Request‑ID (front↔backend, proxy, MTA).

2) Événements “auth:eotp_*” (contrat)
- Nommage:
  - auth:eotp_issued
  - auth:eotp_resent
  - auth:eotp_ok
  - auth:eotp_failed
  - auth:eotp_expired
  - auth:eotp_locked
- Champs (payload log/event; pas de secret ni PII en clair):
  - ts (iso8601), realm, request_id (corr_id si distinct), session_key_hash (SHA‑256 sur session_key tronquée), user_id_hash (si user connu), ip_prefix (/24 v4, /64 v6), ua_hash (sha224), ttl_sec (pour issued/resent), tries_count, resend_count, retry_after_sec (si 429), provider_id (mail) optionnel, bounce_type (hard/soft) optionnel.
- Erreurs uniformes:
  - error: invalid_code | expired | rate_limited | locked | transport_error | provider_bounce
  - Jamais exposer le code OTP ni email.

3) Transport et corrélation (logs, NATS, X‑Request‑ID)
- Logs JSON (studio_core/logging.py):
  - Filtre redact_pii et request_context actifs; champs ci‑dessus intégrés via record_auth_event().
- NATS JetStream (optionnel):
  - Stream “auth” sujet “auth.eotp.*”; consommateur durable côté analytics/ops.
- Corrélation:
  - Nuxt server middleware request-id.ts: génère/propague X‑Request-ID; attache event.context.propagateHeaders.
  - Côté Django: middleware et helpers ajoutent request_id/corr_id aux logs/events.

4) Métriques clés (définitions)
- Compteurs (par realm, par decision):
  - eotp_issued_total, eotp_resent_total, eotp_ok_total, eotp_failed_total, eotp_expired_total, eotp_locked_total.
- Ratios:
  - eotp_success_rate = eotp_ok_total / (eotp_ok_total + eotp_failed_total + eotp_expired_total)
  - eotp_locked_rate = eotp_locked_total / eotp_issued_total
  - eotp_resend_rate = eotp_resent_total / eotp_issued_total
- Latences:
  - eotp_issue_to_ok_seconds (histogram: p50/p90/p99).
- Sécurité/abus:
  - eotp_429_verify_total, eotp_429_resend_total (compteurs par IP/realm).
  - eotp_anomaly_ipasn_total (si enrichissement ASN disponible).
- Délivrabilité:
  - eotp_mail_bounce_total{type=hard|soft, domain} (Sprint 2).

5) Tableaux de bord (dashboards)
- “Funnel e‑OTP” (7 jours, par realm):
  - Issued → Resent → Ok / Failed / Expired / Locked (+ success rate).
- “Fiabilité”:
  - Latence issue→ok (p50/p90/p99), distribution par heure/jour.
- “Sécurité/Abus”:
  - 429 verify/resend, locked rate, heatmap par IP/ASN, répartition ua_hash.
- “Délivrabilité” (post S2):
  - Bounces par domaine, taux par provider, temps d’envoi → réception (si disponible).
- “Opérations”:
  - Purge TTL (lignes purgées/min), backlog pending, erreurs proxy (proxy_*_failed).

6) Alerting (seuils, règles, suppressions)
- Règles principales (exemple; affiner en S6):
  - Spike échecs: eotp_failed_total sur 5 min > baseline*3 ET success_rate < 70% (realm‑scopé) → WARN; < 50% → CRIT.
  - Locked rate: eotp_locked_rate > 5% sur 15 min → WARN; > 10% → CRIT.
  - 429 verify: eotp_429_verify_total sur 5 min > seuil absolu (p.ex. 200) ET variation > 200% → WARN.
  - Bounces (post S2): bounce hard > 1%/h sur domaine → WARN; > 3% → CRIT.
  - Latence: p99(issue→ok) > 15s sur 10 min → WARN.
- Suppressions/anti‑bruit:
  - Fenêtre d’observation glissante, hysteresis (clear < 70% des seuils).
  - Mute par maintenance windows (déploiements).
- Notifications:
  - Canal Ops (chat), + ticket automatique si CRIT > 15 min.

7) Journal inviolable (chaîne de hachage)
- Objectif: garantir intégrité d’une chronologie minimale d’événements auth:eotp_*.
- Approche:
  - Calcul d’un hash chainé H_n = SHA256(H_{n-1} || canonical_json(event_n)).
  - Stockage périodique d’ancres (H_n) dans un log append‑only (ou KV immuable), exportable.
- Périmètre:
  - Sprint 6: implémentation light (fichier/DB dédié + rotation), vérification offline.
  - Pas de secrets dans canonical_json; utiliser identifiants hachés (user_id_hash, session_key_hash).

8) Points d’instrumentation (Django/Nuxt)
- Django:
  - Services e‑OTP (issue/verify/resend): record_auth_event() avec champs requis + labels realm/decision; compteur 429 dans les handlers.
  - Management command purge: compteur purge_total, gauge backlog_pending.
- Nuxt (server):
  - Proxies /api/auth/*: journaliser proxy_*_failed, Retry‑After, X‑Request‑ID, sans cookies.
  - Middleware request-id.ts: s’assurer de la propagation systématique de l’ID.
- Sentry:
  - beforeSend (déjà présent) retire cookies/authorization; tagger realm, request_id (si non sensible).

9) SLO/SLA & revue opérationnelle
- SLO indicatifs (affinage après S1–S3):
  - eotp_success_rate ≥ 90% (hors bounces), p99(issue→ok) ≤ 10s.
  - eotp_locked_rate ≤ 3% (hors attaques), 429_verify taux contrôlé.
- Revue hebdo:
  - Rapport funnels, causes d’échecs dominantes, top ASN/IP, domaines à bounces élevés.
  - Actions: ajustement rate‑limits/cooldowns/flags; suivi d’alertes ouvertes/fermées.

10) Confidentialité & redaction PII
- Interdits:
  - Pas d’OTP/code/email/cookies en clair dans logs/events.
- Obligations:
  - Hash systématique (user_id, session_key, UA); ip_prefix au lieu d’IP pleine.
  - Filtre redact_pii et Sentry beforeSend actifs en prod.
- Rétention:
  - Events non sensibles: conserver selon politique standard; données e‑OTP en DB purgées par TTL.

11) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 06 — Migrations & rollback: ./06-plan-migrations-rollback.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md

12) Points ouverts / TODO
- Finaliser format exact canonical_json pour la chaîne de hachage (Sprint 6).
- Décider métriques d’anomalies (ASN enrichi) et source d’enrichissement.
- Calibrer seuils d’alertes par environnement (dev/stage/prod).
- Définir export/archivage des dashboards et playbooks (runbooks incident).

13) Cycle global S4→S9
- Référence globale du cycle d’observabilité e‑OTP (post Go‑Live):
  - S4: Définition des seuils et règles d’alerting (ops/alerts.json)
  - S6: Journal inviolable (hash‑chain) et vérification (verify_log_chain.py)
  - S7: Scripts Ops (audits/monitoring/résilience) + headers sécurité (CSP/HSTS)
  - S8: Aggregator (JSONL) + Trends (risk_operational_score)
  - S9: Exposition runtime (/debug/eotp-stats), seuil Gate adaptatif (±10%), tests & audits finaux
- Documents:
  - 08 — Monitoring Intelligent: ./08-monitoring-intelligent.md
  - 09 — Feedback Loop: ./09-feedback-loop.md
  - CHANGELOG S9: ./CHANGELOG-S9.md
