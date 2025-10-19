# Rapport final e‑OTP — Revue intégrative pré‑S1
Status: DRAFT
Auteur: Cline (Chef d’intégration technique & SRE auditeur)
Date: 2025-10-17
Version: 1.0 (pré‑S1)

Table des matières
1. Résumé exécutif
2. État de conformité par sprint (S1 → S7)
3. Recommandations d’intégration (obligatoires)
4. Plan de durcissement avant exécution (pré‑S1)
5. Annexes

---

1) Résumé exécutif
🧱 Bloc de validation
- ✅ Acquis
  - Sprint 0 (00–10) complet et cohérent; Todos S1→S7 créés (append‑only) et reliés (index, changelog).
  - Architecture e‑OTP claire: modèle eotp_challenge, Argon2id+pepper, TTL, anti‑rejeu, rate‑limits Redis, observabilité normalisée.
  - Paramètres techniques confirmés (Argon2id m/t/p, Postmark, Celery beat) intégrés aux Todos.
- ⚙️ En cours
  - Canonical JSON v1 + hash chain (S6), outils internes (/tools), runbooks (process/pepper/celery).
- 🚧 À faire
  - Fixer les variables d’environnement (section 3.1) dans .env.dev et documenter dans backend/README.md.
  - Créer les runbooks DRAFT (section 3.3) avant fin S1.
  - Pré‑S1: validations techniques (section 4.2) et checklist sécurité (section 4.3).

Objectif général du projet e‑OTP
- Renforcer l’authentification par code e‑mail (e‑OTP) de manière robuste, observable et sécurisée, compatible Django/Nuxt, sans Turnstile (Rate‑limit Redis), avec activation progressive par flags.

Validation de cohérence documentaire
- Les livrables Sprint 0 (00→10) et les Todos S1→S7 convergent: état cible, risques, observabilité, CI/CD et UX sont alignés. Les dépendances inter‑sprints sont explicitées.

Synthèse des risques majeurs et mitigation (extraits)
- Brute‑force/abus: rate‑limits Redis + backoff + Retry‑After + locked (S4).
- Fuite PII/logs: filtres actifs + Sentry beforeSend + doctrine “no secret/no email” (S0→S7).
- Entropie et charge Argon2id: calibrage m=64MiB, t=3, p=2 (revu S7), bench pré‑S1.
- Délivrabilité: Postmark + DNS (SPF/DKIM/DMARC), webhook bounces (S2).
- Observabilité: événements auth:eotp_* + metrics + alertes + hash chain (S6).
- UX: messages non révélants, timers TTL, cooldown Retry‑After (S3).

Feuille de route finale validée (S1 → S7)
- S1 Backend core → S2 Mail/DNS → S3 UX → S4 Throttling/Rate‑limits → S5 Gate/Passphrase → S6 Observabilité/Alertes → S7 Hardening/DoD.

---

2) État de conformité par sprint (S1 → S7)
🧱 Bloc de validation
- ✅ Acquis
  - Todos détaillés par domaine, DoD, tests, risques, liens vers docs S0.
- ⚙️ En cours
  - Ajout de runbooks et outils internes référencés dans les Todos.
- 🚧 À faire
  - Renseigner Owners par risque (S6/S7), compléter READMEs d’exécution.

Tableau récapitulatif
| Sprint | Statut init | Points forts | Ajustements obligatoires | Liens |
|---|---|---|---|---|
| S1 — Backend Core | DRAFT (todo-S1.md) | Modèle+services+endpoints+purge+flags | Désactiver UNIQUE(session_key,status='pending') et prévoir device_hash optionnel activable S3 | [todos/todo-S1.md](./todos/todo-S1.md) · [02](./02-architecture-cible.md) · [06](./06-plan-migrations-rollback.md) |
| S2 — Mail/DNS | DRAFT (todo-S2.md) | Postmark + fallback SMTP, DNS complet | Vérif automatique DKIM rotation (cron mensuel ou check DNS) | [todos/todo-S2.md](./todos/todo-S2.md) · [08](./08-mail-transport-et-dns.md) |
| S3 — UX e‑OTP | DRAFT (todo-S3.md) | Champ unique, timers TTL backend, a11y, Playwright | Fallback offline (no‑JS) pour “code expiré / pas reçu ?” | [todos/todo-S3.md](./todos/todo-S3.md) · [09](./09-ux-spec-eotp.md) |
| S4 — Throttling | DRAFT (todo-S4.md) | Redis rate‑limits, backoff, Retry‑After | Simulateur d’abus interne pour tester throttling | [todos/todo-S4.md](./todos/todo-S4.md) · [03](./03-threat-model.md) |
| S5 — Gate/Passphrase | DRAFT (todo-S5.md) | Tunnel complet, flags realm | Décider passphrase statique (rotation) ou contextuelle + TTL doc | [todos/todo-S5.md](./todos/todo-S5.md) |
| S6 — Observabilité | DRAFT (todo-S6.md) | Events, metrics, dashboards, alertes | Ajouter test test_canonical_json_deterministic_hash(), finaliser hash chain v1 | [todos/todo-S6.md](./todos/todo-S6.md) · [07](./07-observabilite-alerting.md) |
| S7 — Hardening & DoD | DRAFT (todo-S7.md) | CI “tout vert”, pentests ciblés, runbooks | Intégrer SBoM scan (pip‑audit, npm audit) et outil verify_log_chain.py | [todos/todo-S7.md](./todos/todo-S7.md) |

Interopérabilité S1 ↔ S6 (événements)
- Les services S1 doivent émettre auth:eotp_issued|resent|ok|failed|expired|locked avec format stable.
- S6 consommera ces mêmes événements pour alimenter métriques/alertes; la canonicalisation v1 (ci‑dessous §Annexes B) fige le schéma.

---

3) Recommandations d’intégration (obligatoires)
🧱 Bloc de validation
- ✅ Acquis
  - Paramètres cibles et directives outillées listés ci‑dessous.
- ⚙️ En cours
  - Rédaction des runbooks (DRAFT) et ajout des outils (/tools) en repo.
- 🚧 À faire
  - Renseigner .env.dev et backend/README.md; brancher jobs de vérification (DKIM, alertes).

3.1 Paramètres de configuration à figer (à ajouter à backend/.env.dev et README.md)
| Variable | Valeur reco | Contexte |
|---|---|---|
| EOTP_TTL | 300 | Durée de validité d’un code (s) |
| MAX_TRIES | 3 | Tentatives avant lock |
| COOLDOWN_SECONDS | 30 | Délai minimal entre deux verify/resend |
| EOTP_PEPPER | (secret env distinct) | Pepper e‑OTP (jamais en DB) |
| HASH_CHAIN_ALGO | SHA256 | Canonicalisation stable |
| ARGON2_M | 64MiB | Charge mémoire |
| ARGON2_T | 3 | Itérations |
| ARGON2_P | 2 | Threads |

3.2 Outils internes à créer (/tools) — documentation (≤ 10 lignes)
- tools/test_backoff.sh
  - Usage: simule spam verify/resend pour mesurer Retry‑After, 429 et backoff; accepte BASE_URL, USER/PASS.
  - Exemple: ./tools/test_backoff.sh http://127.0.0.1:3100 20 req/min
  - Sorties attendues: taux 429, Retry‑After moyen, locked rate.
- tools/verify_log_chain.py
  - Usage: lit un fichier d’événements canonical_json v1, recalcul H_n=SHA256(H_{n-1}||json) et vérifie l’ancre.
  - Exemple: python tools/verify_log_chain.py --input events.ndjson --anchor anchor.txt
  - Sorties: “OK” + dernier hash; ou “Mismatch at line N”.
- tools/obs_sanity.sh
  - Usage: vérifie présence de séries eotp_* et règles d’alerte (Prom/Grafana API).
  - Exemple: ./tools/obs_sanity.sh --realm dojo
  - Sorties: liste métriques présentes + statut alert rules.

3.3 Runbooks à créer (DRAFT avant fin S1)
- docs/auth/eotp/runbooks/runbook-process.md — cycle alerte → action → ticket → fermeture (RACI + SLA + escalade).
- docs/auth/eotp/runbooks/rotate_pepper.md — procédure de rotation du pepper (pré‑checks, déploiement, post‑checks).
- docs/auth/eotp/runbooks/celery-beat-purge.md — diagnostic purge TTL, backlog, VACUUM ANALYZE.

3.4 Ajustements techniques obligatoires (à intégrer dans les Todos)
- S1: désactiver UNIQUE(session_key,status='pending'); introduire device_hash optionnel (activation S3).
- S2: vérification mensuelle DKIM rotation (cron ou job d’observabilité).
- S3: fallback offline “code expiré/pas reçu ?” sans JS.
- S4: simulateur d’abus interne (driver des rate‑limits).
- S5: décider passphrase statique (rotation) vs contextuelle (documenter TTL).
- S6: ajouter test test_canonical_json_deterministic_hash().
- S7: SBoM scans (pip‑audit, npm audit) + CLI verify_log_chain.py.

---

4) Plan de durcissement avant exécution (pré‑S1)
🧱 Bloc de validation
- ✅ Acquis
  - Tâches pré‑migration, perf, audit sécu, sanity Celery listées ci‑dessous.
- ⚙️ En cours
  - Outillage et scripts de vérification.
- 🚧 À faire
  - Exécuter et archiver les résultats (CI artifacts/notes).

4.1 Tâches spécifiques à exécuter avant S1
- Fixer et commiter .env.dev (valeurs §3.1) + README.md backend.
- Revue S1 Todo: supprimer UNIQUE(session_key,status='pending'); option device_hash documentée.

4.2 Vérifications de cohérence & prérequis d’environnement
- Tests pré‑migration DB
  - Vérifier schéma actuel; dry‑run: python manage.py makemigrations --check
- Tests de performance Argon2id
  - Mesurer latence issue/verify + CPU (p50/p95/p99); ajuster m/t/p si besoin
- Audit sécurité
  - pip‑audit, bandit, safety; npm audit (front)
- Sanity Celery
  - celery inspect scheduled (tâche eotp_purge_expired visible)

4.3 Checklist de sécurité (extraits)
- Anti‑rejeu strict (verify: one‑time), constant‑time compare, logs PII‑safe.
- Isolation realm (cookies/sessions), CSRF double‑submit, Retry‑After systématique.
- Secrets hors repo (EOTP_PEPPER), Sentry beforeSend ok, DKIM/SPF/DMARC prêts.

---

5) Annexes
🧱 Bloc de validation
- ✅ Acquis
  - Table Owners (proposition), schéma canonical JSON v1 et exemple hash, liste outils/scripts.
- ⚙️ En cours
  - Génération de l’ancre SHA256 et script de vérification.
- 🚧 À faire
  - Actualiser Owners nominativement (SRE/Sécu/Produit).

Annexe A — Tableau des Owners (risque → responsable)
| ID Risque | Titre | Owner (proposé) | Lien |
|---|---|---|---|
| R‑SEC‑001 | Brute‑force OTP | SRE Lead | [10](./10-risques-et-contingences.md) |
| R‑SEC‑005 | Fuite PII | Security Officer | [10](./10-risques-et-contingences.md) |
| R‑OPS‑002 | Provider e‑mail indispo | Ops On‑Call | [10](./10-risques-et-contingences.md) |
| R‑OPS‑003 | Charge Argon2id | Platform Eng | [10](./10-risques-et-contingences.md) |
| R‑UX‑001 | Frictions (UX) | PM + UX | [10](./10-risques-et-contingences.md) |

Annexe B — Canonical JSON v1 & hash chain (référence)
- Ordre des champs (exemple pour auth:eotp_ok):
  ts, realm, event, request_id, corr_id, session_key_hash, user_id_hash, ua_hash, ip_prefix, ttl_sec, tries_count, resend_count
- Exemple (minifié):
  {"ts":"2025-10-17T09:00:00Z","realm":"dojo","event":"auth:eotp_ok","request_id":"R123","corr_id":"C456","session_key_hash":"…","user_id_hash":"…","ua_hash":"…","ip_prefix":"203.0.113.0/24","ttl_sec":300,"tries_count":1,"resend_count":0}
- Hash chain:
  H_0="0000…0000"; H_n=SHA256(H_{n-1}||canonical_json(event_n)) (UTF‑8, sans espace)
- Exemple de calcul (pseudo):
  echo -n "$H_PREV$JSON" | sha256sum
- Outil de vérification: tools/verify_log_chain.py (cf. §3.2)

Annexe C — Liste des outils/scripts à créer (/tools)
- tools/test_backoff.sh — simulation abuse/backoff; sortie taux 429/Retry‑After/locked
- tools/verify_log_chain.py — validation ancre hash chain
- tools/obs_sanity.sh — sanity metrics/alertes eotp_*

Annexe D — Références croisées
- Sprints: [index Todos](./todos/index.md) · [CHANGELOG-TODO](./todos/CHANGELOG-TODO.md)
- Docs S0: [00](./00-vision-et-portee.md) [01](./01-cartographie-existant.md) [02](./02-architecture-cible.md) [03](./03-threat-model.md) [04](./04-plan-de-sprints.md) [05](./05-test-strategy.md) [06](./06-plan-migrations-rollback.md) [07](./07-observabilite-alerting.md) [08](./08-mail-transport-et-dns.md) [09](./09-ux-spec-eotp.md) [10](./10-risques-et-contingences.md)

Annexe E — Hash SHA256 du corpus documentaire (audit)
- Commande de génération (à lancer au tag “v0-sprint0bis”):
  - Linux: find docs/auth/eotp -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
- Valeur: À RENSEIGNER LORS DU TAG (append dans ce rapport)

Signature
Rapport généré par Cline — revue intégrative pré‑S1
