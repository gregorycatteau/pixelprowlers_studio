# Todo — Sprint S2 (Mailer & Domaine — Postmark, DNS)
Status: DRAFT
Sprint: S2
Auteur: Cline (Analyste/Architecte + SRE)
Date: 2025-10-17

Références (Sprint 0)
- 02 — Architecture cible: ../02-architecture-cible.md
- 04 — Plan de sprints: ../04-plan-de-sprints.md
- 05 — Stratégie de tests: ../05-test-strategy.md
- 07 — Observabilité & alerting: ../07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ../08-mail-transport-et-dns.md
- 10 — Risques & contingences: ../10-risques-et-contingences.md

Objectif du sprint
- Délivrer une abstraction e‑mail robuste (provider principal Postmark, fallback SMTP TLS) pour l’émission des e‑OTP, avec configuration DNS complète (SPF/DKIM/DMARC, MTA‑STS, TLSRPT) et collecte des bounces.
- Aucune fuite de PII/secret; contenu e‑mail minimaliste sans liens sensibles. Webhook de bounces opérationnel.

Checklist technique (append‑only)
Backend (Django)
- ⏳ Abstraction Mailer (interface + impl Postmark) — [08][02]
  Acceptation: classe mailer postmark utilisant clé API via secrets; timeouts; retries minimes; logs PII‑safe; test unitaire stub.
  Dép: conf env POSTMARK_API_TOKEN, POSTMARK_FROM.
- ⏳ Intégration service e‑OTP → mailer (issue) — [02]
  Acceptation: eotp_issue appelle mailer si flag eotp_enabled; en test/APP_ENV=test, _peek reste prioritaire; code jamais loggué.
  Dép: S1 services/flags.
- ⏳ Fallback SMTP TLS (libs Django) — [08]
  Acceptation: settings fallback SMTP (host, port, TLS, user/pass) via secrets; bascule contrôlée par flag/feature “mailer_backend=smtp”.
- ⏳ Circuit‑breaker provider — [08][10]
  Acceptation: si taux d’échec > seuil sur 5 min, bascule vers fallback et alerte (event + metric); doc d’exploitation.
- ⏳ Webhook bounces (endpoint dédié) — [08][07]
  Acceptation: endpoint POST /api/mail/bounces/provider (auth simple par signature provider); payload réduit (hash email, type hard/soft, domain); tests intégration Pytest.
- ⏳ Stockage minimal bounces (optionnel) — [08][07]
  Acceptation: modèle ou KV gardant bounces récents (clé domain/type/cnt) pour métriques; aucune PII en clair.
- ⏳ Secrets management — [08][10]
  Acceptation: variables Postmark/SMTP en env/secret manager; rotation documentée; aucun secret en repo.

DNS & Domaine
- ⏳ SPF (provider Postmark + éventuel SendGrid futur) — [08]
  Acceptation: enregistrements TXT publiés pour domaine/sous‑domaine d’envoi; dig/nslookup OK.
- ⏳ DKIM 2048 (Postmark) — rotation semestrielle — [08]
  Acceptation: sélecteurs configurés; “pass” côté provider; doc de rotation.
- ⏳ DMARC progression (p=none→quarantine→reject) — [08]
  Acceptation: démarrer “p=none”; boîtes dmarc-reports@ prêtes; plan d’escalade <1% hard bounce après 7j.
- ⏳ MTA‑STS (enforce), TLSRPT — [08]
  Acceptation: _mta-sts TXT + policy publiée; _smtp._tls TXT; vérif basique de disponibilité.

Front (Nuxt) / UX
- ⏳ Aucun changement UI obligatoire en S2 — [09]
  Acceptation: les écrans e‑OTP restent côté S3; ici seules capacités d’envoi évoluent.

Tests (QA)
- ⏳ Pytest unitaires: mailer postmark stub + fallback smtp stub — [05]
  Acceptation: succès logique sans appel externe; PII‑safe.
- ⏳ Pytest intégration: webhook bounces (signature/format), intégration issue→envoi (mock provider) — [05]
  Acceptation: retours 2xx/4xx conformes; métriques incrementées; aucun secret en logs.
- ⏳ Playwright: N/A (pas d’effet visuel) — [05]
  Acceptation: N/A S2.
- ⏳ Vitest: N/A (S3) — [05]
  Acceptation: N/A.

Observabilité
- ⏳ Événements: auth:eotp_issued (enrichi “provider_id”), auth:eotp_resent, auth:provider_error, auth:mail_bounce — [07]
  Acceptation: events émis aux étapes; PII‑safe; corr_id présent.
- ⏳ Métriques: eotp_mail_send_total, eotp_mail_bounce_total{type,domain}, ratio bounces/send — [07]
  Acceptation: métriques visibles; tests Pytest valident incréments.
- ⏳ Dashboards: volet délivrabilité — [07]
  Acceptation: panneaux basiques (bounces par domaine, évolution).

Ops (SRE)
- ⏳ Runbook “Drop Délivrabilité” (provider down, bounces spike) — [08][10]
  Acceptation: procédure claire (bascule fallback, throttling, contact provider).
- ⏳ Rotation secrets SMTP/Postmark — [08][10]
  Acceptation: doc rotation + calendrier; test de rotation sur env de test.
- ⏳ DMARC/TLSRPT boîtes — [08]
  Acceptation: dmarc-reports@ et tlsrpt@ créées/monitorées; parsing minimal.

Critères d’acceptation (DoD S2)
- Envoi e‑mail e‑OTP via Postmark opérationnel en stage/test (mock en CI).
- Fallback SMTP TLS fonctionnel et documenté; circuit‑breaker validé.
- DNS: SPF/DKIM “pass” confirmés; DMARC p=none actif; MTA‑STS/TLSRPT publiés.
- Webhook bounces opérationnel (tests intégration) + métriques exposées.
- Aucun secret/PII en clair dans logs/events; events et métriques conformes [07].

Dépendances
- S1 services/flags opérationnels (issue/resend).
- Accès DNS domaine (pixelprowlers.io) et compte Postmark.

Risques spécifiques (S2) & mitigation
- 🔒 Délivrabilité (réputation domaine) — Mitigation: sous‑domaine dédié, warm‑up, monitoring bounces, DMARC progressive. Ref: [10].
- 🔒 Provider indisponible — Mitigation: fallback SMTP + circuit‑breaker; alerte. Ref: [10].
- 🔒 Mauvaise signature webhook — Mitigation: vérifier signature provider; rejeter sinon; tests. Ref: [10].

Tests & validation — commandes
- Pytest (backend):
  - pytest -q -k "mail or bounce"
- Outils DNS (manuel ops):
  - dig TXT pixelprowlers.io, dig TXT _dmarc.pixelprowlers.io, dig TXT _mta-sts.pixelprowlers.io

Documentation / Appendices
- Mettre à jour: [08] (sélecteurs DKIM, DMARC progression), [07] (events/métriques), [04] (jalons S2).
- Append later: logs anonymisés de tests, captures des dashboards délivrabilité.

Notes techniques confirmées à intégrer (rappel)
- Provider principal: ✅ Postmark; fallback SMTP TLS (rotation creds).
- DMARC: p=none → p=quarantine → p=reject après 7j si hard bounce < 1%.
- Boîtes: dmarc-reports@ et tlsrpt@ à créer avant go‑live.
- DKIM 2048, rotation semestrielle; sélecteurs multiples.

Append‑only
- Ne pas supprimer les entrées; ajouter des sous‑tâches/observations datées.
