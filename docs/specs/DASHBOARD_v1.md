# DASHBOARD v1 — KPIs, Sources, Seuils, Agrégation

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références croisées:
- docs/specs/EVENTS_v1.md
- docs/specs/RBAC_v1.md
- docs/specs/SECURITY_BASELINES.md
- docs/specs/ROOMS_v1.md
- docs/specs/SOCKETS_BRIDGE_v1.md
- docs/checklists/QA_E2E.md
- docs/specs/GOVERNANCE_v1.md

Statut: v1 (contrats figés pour Sprint 03)

-----------------------------------------------------------------------

1) Objet & portée
- Définir les KPIs v1 du Global Dashboard, leurs sources, règles d’agrégation, seuils d’alerte et contrats JSON de restitution.
- Garantir un accès lecture-only (RBAC v1) et une traçabilité forte (correlation_id dans les logs d’accès).
- Fournir des exemples canoniques et des validations (jsonschema/zod) pour éviter les régressions.

Hors de portée (v1):
- KPIs métiers avancés (au-delà des 4 KPIs essentiels).
- Drill-down de logs/traçage complexe; exposer uniquement des métriques agrégées et sûres.

-----------------------------------------------------------------------

2) KPIs v1 (définition)

2.1 Liste des KPIs
- KPI: volume24h
  - Description: volume de messages sur 24h glissantes (par tranche horaire).
  - Source: comptage d’événements pertinents (cf. 3.1).
  - Fenêtre: 24h (points horaires: 24).
  - Endpoint: GET /api/kpis/volume24h

- KPI: errors24h
  - Description: erreurs par criticité sur 24h (totaux et éventuellement série horaire).
  - Source: événements error:occurred.
  - Fenêtre: 24h.
  - Endpoint: GET /api/kpis/errors24h

- KPI: latency
  - Description: latence moyenne de stream (p50/p90) sur 15 min et 24h.
  - Source: durée corrélation chat:user_message → dernier chat:agent_stream (done=true).
  - Fenêtre: 15 min (courte) et 24h (large).
  - Endpoint: GET /api/kpis/latency

- KPI: rooms
  - Description: rooms actives (courant) et pic 24h.
  - Source: état courant + historisation (join/leave/closed) dans les events sockets.
  - Fenêtre: instantané + 24h.
  - Endpoint: GET /api/kpis/rooms

2.2 Codage couleur (seuils par défaut — configurables)
- Severities: ok (green), warn (amber), error (red), unknown (grey).
- latency.p90 (fenêtre 15 min):
  - ok < 2000 ms, warn [2000..3500] ms, error > 3500 ms
- errors24h.rate (erreurs/total événements pertinents):
  - ok < 1%, warn [1..3]%, error > 3%
- rooms.active (en fonction d’une capacité max “rooms_capacity”):
  - ok ≤ 70% capacité, warn (70..90]%, error > 90%
- volume24h: informatif (pas d’alerte par défaut).

-----------------------------------------------------------------------

3) Sources & agrégations

3.1 Sources d’événements (EVENTS v1)
- volume24h (messages):
  - Inclure:
    - chat:user_message
    - chat:agent_stream (option: compter uniquement le “done=true” ou tous les chunks; par défaut, seulement “done=true” pour refléter des réponses complètes)
    - widget:update (optionnel; par défaut OFF pour préserver la sémantique “chat”)
    - system:alert (optionnel; par défaut OFF)
  - Paramètre de déploiement: “volume.include_kinds” (liste blanche)

- errors24h:
  - Inclure: error:occurred (payload.severity ∈ {warn, error, critical})
  - Agrégation par criticité et total.

- latency:
  - Pour chaque correlation_id issu d’un chat:user_message:
    - Calculer durée = ts(chat:agent_stream done=true) - ts(chat:user_message)
    - Exclure si done manquant, si durée hors bornes (ex: > 5 min par défaut) — classer en outliers (métrique séparée optionnelle)
  - Calculer p50 et p90 sur fenêtres 15 min et 24h (glissantes).

- rooms:
  - État courant: nombre de rooms status=active (ROOMS v1).
  - Pic 24h: maximum des rooms actives observées dans les dernières 24h.
  - Sources: events sockets (join_room, leave_room, system_update kind=room_closed) + stockage d’état.

3.2 Règles d’agrégation
- Fenêtres:
  - 24h: bornes [now-24h, now], bucket horaire (24 points).
  - 15 min: bornes [now-15m, now], bucket min (15 points) pour calculs internes, exposer p50/p90 agrégés.
- Horodatage:
  - Tous les calculs utilisent UTC (ISO 8601), alignement par minute/heure entière.
- Normalisation:
  - Les compteurs et durées sont numériques; pas de null; préférer 0 pour “manque”.
- Seuils:
  - Appliquer les règles de 2.2; l’état global du dashboard peut prendre la pire severité de tous les KPIs qui ont des seuils (latency, errors, rooms).
- Données aberrantes:
  - Latency: ignorer valeurs < 0 ou > “max_latency_ms” (config: 300000 ms par défaut), compteur outliers pour observabilité (non affiché v1).

3.3 Rafraîchissement & cadence
- Événement cadencer: metrics:tick (EVENTS v1) peut déclencher un refresh UI contrôlé.
- Poll côté front: intervalle recommandé 5–30s selon KPI.
- Serveur: conserver caches en mémoire (TTL 5–30s) et ETag/If-None-Match.

-----------------------------------------------------------------------

4) Contrats JSON (type-safe)

4.1 Enveloppe de réponse (commune)
- Champs communs:
  - kpi: string (ex: “volume24h”)
  - ts: string (ISO 8601 UTC) — horodatage de génération
  - window: { since: string, until: string } — bornes inclusives
  - values: object — structure spécifique au KPI
  - status: { state: "ok|warn|error|unknown", reason?: string, thresholds?: object }
  - correlation_id?: string (UUID v4) — renvoyé si fourni côté requête (optionnel)
- Recommandations HTTP:
  - Cache-Control: public, max-age=5–30
  - ETag: version forte/weak selon convenance
  - Content-Type: application/json; charset=utf-8

Schéma (jsonschema, draft 2020-12) — enveloppe générique:
    {
      "$schema": "https://json-schema.org/draft/2020-12/schema",
      "title": "KPIEnvelope v1",
      "type": "object",
      "required": ["kpi","ts","window","values","status"],
      "additionalProperties": false,
      "properties": {
        "kpi": { "type": "string" },
        "ts": { "type": "string", "format": "date-time" },
        "window": {
          "type": "object",
          "required": ["since","until"],
          "additionalProperties": false,
          "properties": {
            "since": { "type": "string", "format": "date-time" },
            "until": { "type": "string", "format": "date-time" }
          }
        },
        "values": { "type": "object" },
        "status": {
          "type": "object",
          "required": ["state"],
          "additionalProperties": true,
          "properties": {
            "state": { "type": "string", "enum": ["ok","warn","error","unknown"] },
            "reason": { "type": "string" },
            "thresholds": { "type": "object" }
          }
        },
        "correlation_id": {
          "type": "string",
          "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
        }
      }
    }

4.2 volume24h (GET /api/kpis/volume24h)
- values:
  - total: number (entier ≥ 0)
  - series: array[24] of { t: string (ISO hour start), count: number }
- status:
  - state: always "ok" (par défaut), reason?: string

Exemple:
    {
      "kpi": "volume24h",
      "ts": "2025-10-13T06:30:15Z",
      "window": { "since": "2025-10-12T06:30:15Z", "until": "2025-10-13T06:30:15Z" },
      "values": {
        "total": 1287,
        "series": [
          { "t": "2025-10-12T07:00:00Z", "count": 42 },
          { "t": "2025-10-12T08:00:00Z", "count": 51 }
          // ... total 24 points
        ]
      },
      "status": { "state": "ok" }
    }

4.3 errors24h (GET /api/kpis/errors24h)
- values:
  - totals: { info: number, warn: number, error: number, critical: number, all: number }
  - rate: number (erreurs / événements pertinents; 0..1)
  - by_hour?: array[24] of { t: string, warn: number, error: number, critical: number }
- status:
  - state via seuils rate: ok|warn|error (cf. 2.2)
  - thresholds: { ok_lt: 0.01, warn_lte: 0.03 } (exemple de rappel)

Exemple:
    {
      "kpi": "errors24h",
      "ts": "2025-10-13T06:30:15Z",
      "window": { "since": "2025-10-12T06:30:15Z", "until": "2025-10-13T06:30:15Z" },
      "values": {
        "totals": { "info": 12, "warn": 19, "error": 7, "critical": 1, "all": 39 },
        "rate": 0.012,
        "by_hour": [
          { "t": "2025-10-12T07:00:00Z", "warn": 1, "error": 0, "critical": 0 }
          // ... 24 points
        ]
      },
      "status": {
        "state": "warn",
        "reason": "errors rate 1.2% within [1..3]%",
        "thresholds": { "ok_lt": 0.01, "warn_lte": 0.03 }
      }
    }

4.4 latency (GET /api/kpis/latency)
- values:
  - p50_ms_15m: number
  - p90_ms_15m: number
  - p50_ms_24h: number
  - p90_ms_24h: number
  - samples_15m: number
  - samples_24h: number
  - outliers_ignored?: number
- status:
  - state via p90_ms_15m seuils (cf. 2.2)

Exemple:
    {
      "kpi": "latency",
      "ts": "2025-10-13T06:30:15Z",
      "window": { "since": "2025-10-12T06:30:15Z", "until": "2025-10-13T06:30:15Z" },
      "values": {
        "p50_ms_15m": 910,
        "p90_ms_15m": 2400,
        "p50_ms_24h": 980,
        "p90_ms_24h": 2600,
        "samples_15m": 143,
        "samples_24h": 3187,
        "outliers_ignored": 2
      },
      "status": {
        "state": "warn",
        "reason": "latency p90 15m = 2400 ms within [2000..3500]"
      }
    }

4.5 rooms (GET /api/kpis/rooms)
- values:
  - active_now: number
  - peak_24h: number
  - capacity?: number
- status:
  - state via ratio active_now/capacity (si capacity fourni); sinon "unknown"

Exemple:
    {
      "kpi": "rooms",
      "ts": "2025-10-13T06:30:15Z",
      "window": { "since": "2025-10-12T06:30:15Z", "until": "2025-10-13T06:30:15Z" },
      "values": { "active_now": 7, "peak_24h": 12, "capacity": 20 },
      "status": { "state": "ok", "reason": "7/20 (35%) ≤ 70%" }
    }

-----------------------------------------------------------------------

5) Endpoints & Accès

5.1 Endpoints (lecture-only)
- GET /api/kpis/volume24h
- GET /api/kpis/errors24h
- GET /api/kpis/latency
- GET /api/kpis/rooms

5.2 Paramètres communs (optionnels)
- ?since=ISO8601&until=ISO8601 (par défaut: 24h)
- ?tz=UTC (uniquement pour formatage; calculs en UTC)
- ?correlation_id=uuid-v4 (renvoyé tel quel dans la réponse; utile pour corréler la requête dans les logs)
- Contrôles:
  - since ≤ until; bornes raisonnables (ex: max 7 jours en v1)

5.3 RBAC v1
- viewer: lecture-only autorisée pour tous les KPIs
- ops: idem + accès diagnostics agrégés (logs d’accès côté back)
- superuser: idem + historique d’alertes (hors scope v1)
- agent: deny par défaut

5.4 Sécurité & Performance
- Rate limiting: 1 req/sec par utilisateur avec burst faible
- Cache: TTL 5–30s; ETag/If-None-Match; 304 Not Modified
- Logs d’accès corrélables:
  - Chaque requête logguée avec correlation_id, actor, role, path, latency_ms, status, hash_prev/hash_curr

-----------------------------------------------------------------------

6) Contrôles & validations

6.1 Validation schémas
- Enveloppe KPIEnvelope v1: requis pour toutes les réponses
- Spécifique à chaque KPI:
  - volume24h: series length=24
  - errors24h: totaux non négatifs; rate ∈ [0,1]
  - latency: p50/p90 non négatifs; samples ≥ 0
  - rooms: active_now, peak_24h ≥ 0; capacity si présent ≥ 1

6.2 Intégrité temporelle
- window.since < window.until
- ts ∈ [since..until] (approx; tolérance quelques secondes)

6.3 Oracles (échantillons)
- latency: p90_ms_15m ≥ p50_ms_15m
- errors24h: totals.all = info+warn+error+critical (si “info” est pratiqué dans pipeline)
- volume24h: total = somme(series.count)

6.4 Alerte (system:alert)
- Si status.state passe à error pour latency ou errors24h:
  - Émettre un system:alert (EVENTS v1) avec payload: severity=error|critical (selon dépassement), code, message, context (kpi, observed, threshold)

-----------------------------------------------------------------------

7) Exemples d’alertes (EVENTS v1)

Alerte latence p90 élevée:
    {
      "type": "system:alert",
      "ts": "2025-10-13T06:31:00Z",
      "actor": { "id": "system_monitor", "kind": "system" },
      "thread_id": "th_dashboard",
      "correlation_id": "9e27f766-0c2d-4784-9b21-5c0b48cc3c77",
      "payload": {
        "severity": "warn",
        "code": "LATENCY_P90_HIGH",
        "message": "Latency p90 15m exceeds warn threshold",
        "context": { "observed_ms": 2400, "threshold_ms": 2000, "window": "15m" }
      }
    }

-----------------------------------------------------------------------

8) Compatibilité & versionnage

- v1 stable pour Sprint 03
- Ajouts compatibles:
  - Champs optionnels dans values/status
  - Nouvelles séries fines (ex: by_minute) sans rupture
- Ruptures (exigent v2):
  - Changement sémantique des champs, renommage, suppression de champs requis
- Rollback documentaire:
  - Rétablir la version précédente; revalider exemples canoniques; relancer e2e “4 KPIs + 1 alerte simulée”

-----------------------------------------------------------------------

9) Sécurité (gates)

- RBAC lecture-only (viewer, ops, superuser); agent: deny par défaut
- Journaux d’accès:
  - correlation_id obligatoire (si fourni par client, sinon généré côté serveur)
  - hash_prev/hash_curr pour chaînage (audit inviolable)
- CORS/Origin:
  - Limiter connect-src (CSP) du front aux APIs internes
- Anti-abus:
  - Throttling, quotas par utilisateur
- Données:
  - Validation stricte (jsonschema/zod) avant rendu; pas de secrets; redaction si nécessaire

Gate de promotion Sprint 03:
- e2e “4 KPIs + 1 alerte simulée” vert (Playwright)
- RBAC viewer lecture-only vérifié
- Logs corrélés et hashés pour chaque fetch KPI
- Schémas validés sans erreur

-----------------------------------------------------------------------

10) Tests & QA (synthèse)

- e2e:
  - Ouvrir Dashboard → afficher 4 KPIs (mock stabilisé)
  - Déclencher condition d’alerte (errors24h.rate > seuil) → system:alert émis
- Intégration:
  - Validation schémas de chaque endpoint
  - Vérifier calculs (somme/ratios, p50/p90)
- Non-régression:
  - Snapshots d’exemples canoniques (réponses anonymisées)
- Observabilité:
  - Log d’accès KPI: actor, role, kpi, params, latency_ms, status, correlation_id

-----------------------------------------------------------------------

11) SLO (placeholder) et Télémétrie

- Télémétrie/OTel: différée (planifiée dans une version ultérieure; non bloquant v1).
- SLO-STREAM-P90 (planned): p90 latence stream ≤ 2.5s sur 95% des heures (placeholder v1).
- Error Budget hebdomadaire (planned): tolérance 5 % d’heures hors SLO par semaine.
- Exigence d’affichage (v1): afficher ces deux lignes (SLO-STREAM-P90 et Error Budget hebdo) en “planned” sur le Dashboard.
- Politique de cache KPIs: confirmée (TTL 5–30s; ETag/If-None-Match conservés).

-----------------------------------------------------------------------

Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale de la spécification DASHBOARD v1 (KPIs, sources d’agrégation, seuils/codage couleur, endpoints/contrats JSON, sécurité RBAC lecture-only, tests & alerte).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — SLO placeholder ajouté (p90 ≤ 2.5s sur 95% des heures, planned), télémétrie/OTel différée, politique cache KPIs confirmée (TTL 5–30s + ETag/If-None-Match).
- 2025-10-13 — Alice (Lead Orchestrator): Patch v1b — Ajout SLO-STREAM-P90 et Error Budget hebdomadaire (état “planned”) + exigence d’affichage; lien vers GOV ajoutée dans Références croisées.
