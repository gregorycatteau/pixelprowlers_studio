# COCKPIT_TEMPLATE v1 — Spécification (Nuxt 4 + Tailwind 4)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références croisées:
- docs/specs/EVENTS_v1.md
- docs/specs/RBAC_v1.md
- docs/specs/WIDGET_REGISTRY.md
- docs/specs/SECURITY_BASELINES.md
- docs/specs/GOVERNANCE_v1.md
- docs/roadmaps/Sprint_01_Cockpit_Template.md

Statut: v1 (contrats figés pour Sprints 00–03)

-----------------------------------------------------------------------

1) Objet & portée
- Définir le template standard d’un Cockpit agent (route unique), ses composants, leur lifecycle, et les contrats d’intégration front↔back↔widgets.
- Garantir la traçabilité par correlation_id, l’application des baselines sécurité, et la compatibilité avec EVENTS v1 et RBAC v1.
- Cible technique: Nuxt 4 (app directory) + Tailwind 4.
- Hors de portée (v1): widgets métiers complexes (seulement un widget factice read-only en e2e), design system avancé.

-----------------------------------------------------------------------

2) Layout (structure UI figée)

- Route: /cockpits/{agent_slug}
- Disposition:
  - Header
    - AgentSelect (optionnel selon RBAC)
    - Status (transport SSE/WS, rôle courant)
  - Main
    - ChatPanel (gauche)
    - WidgetHost (droite)
  - Aside
    - Logs récents (corrélés)
    - MetricsStrip (latence moyenne, erreurs 5m, transport)

- Grille Tailwind (indicative):
  - Desktop: grid-cols-[1fr_1fr] sur Main; Aside en colonne étroite ou drawer.
  - Mobile: stack vertical (Header, ChatPanel, WidgetHost, Aside collapsible).

- États d’accessibilité/UX:
  - Actions masquées/désactivées selon RBAC.
  - Focus management pour saisie Chat.
  - États visuels: idle, connecting, ready, error, reconnecting.

-----------------------------------------------------------------------

3) Lifecycle (FSMs minimales)

3.1 Cockpit (global)
- idle → connecting (init transport + chargement contexte) → ready (stream actif + widget monté)
- ready → error (échec transport ou widget) → reconnecting (backoff exponentiel) → ready
- ready → unmount (navigation/fermeture) → idle

3.2 MessageStream
- idle → connecting (abonnement SSE/WS) → streaming (réception events chat:agent_stream)
- streaming → error (perte transport) → reconnecting → streaming
- Done condition: reçoit un chunk done=true par (thread_id, correlation_id)

3.3 WidgetHost
- idle → mount (sandbox iframe + handshake) → ready
- ready → state_changed (widget:update) → ready
- ready → error (CSP/postMessage/origin) → recovering | unmount
- recovering → ready | error → unmount
- unmount remet à idle

-----------------------------------------------------------------------

4) Composants & contrats (interfaces v1)

4.1 ChatPanel
- Rôle: collecte la saisie utilisateur et poste la requête au backend, affiche l’ack et l’écho local, déclenche MessageStream.
- Actions:
  - POST /api/agents/{agent_slug}/chat (mock en v1) avec ChatRequest.
  - Journalise un log UI corrélé à chaque action critique.
- Props (conceptuelles):
  - actor: { id, role }, agentSlug: string, threadId?: string
  - transport: { kind: "sse"|"ws", url: string }
- Événements (émis côté front):
  - submit(message, thread_id?)
  - ack(received: ChatResponseAck)
  - error(err)
- Contrats:
  - ChatRequest (JSON)
    {
      "message": "string (1..2000)",
      "thread_id": "string (optional)"
    }
  - ChatResponseAck (JSON)
    {
      "accepted": true,
      "correlation_id": "uuid-v4"
    }
- Exigences:
  - Injecter/propager correlation_id vers MessageStream et logs front.
  - Appliquer CSRF + session binding (SECURITY_BASELINES).
  - RBAC v1: write:chat requis (superuser autorisé; ops/viewer: deny).

4.2 MessageStream
- Rôle: consommer et afficher les événements `chat:agent_stream` (EVENTS v1), bufferiser/fusionner par correlation_id et thread_id.
- Entrées:
  - source: SSE (recommandé) ou WS (fallback), selon config globale.
  - filters: { thread_id?, correlation_id }
- Sorties:
  - render(chunks[]), metrics (latence, erreurs par fenêtre)
- Contrats:
  - Consomme des EVENTS v1: type="chat:agent_stream" avec champs communs et payload { chunk, index, done, latency_ms?, model? }.
- Exigences:
  - Group-by (thread_id, correlation_id), index monotone par flux.
  - timeouts et backoff (reconnecting) documentés.
  - Journalise les transitions d’état (connecting→streaming, error, reconnecting).

4.3 WidgetHost
- Rôle: monter, isoler et piloter des widgets déclarés dans le registre; exposer une API minimaliste; appliquer deny-by-default.
- API v1:
  - mount(widgetId, version?, opts?): Promise<MountResult>
  - unmount(): Promise<void>
  - loadContext({ project?, agent }): Promise<void>
- Sécurité:
  - Widgets internes only (v1): internalOnly: true; aucune origin externe autorisée via registry; CSP host (référence) = default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; iframe sandbox="allow-scripts allow-same-origin".
  - PostMessage strict: messages doivent respecter un schéma (zod/jsonschema) avec champs obligatoires { type, nonce, origin, capability, payload, correlation_id }; origin ∈ allowlist interne; contrôle de capability à chaque message; types inconnus/origins non autorisées/capabilities absentes → reject + log sécurité.
  - Deny-by-default sur toute capability write:*.
- Contrats postMessage (host↔widget):
  - Host→Widget
    - widget:init { correlation_id, actor, agent, capabilities_allowed[] }
    - widget:context { project?, agent }
  - Widget→Host
    - widget:ready { version, capabilities_declared[] } → vérif ⊆ capabilities_allowed
    - widget:state { state_delta } → émet `widget:update` (EVENTS v1, action=state_changed)
  - Rejets:
    - Toute requête write:* → reject avec erreur RBAC + log + (optionnel) system:alert
- Émissions EVENT v1:
  - widget:update (action=mount|unmount|state_changed) avec champs communs et correlation_id courant.
- Exigences:
  - Valider le scope d’un widget (registry.scope contient agentSlug).
  - Refuser le mount si capabilities_declared ∉ registry.capabilities.
  - Aucun inline script/style dans l’iframe; CSP viol = error → unmount; Safe Mode (fallback UI): désactive le widget, conserve le chat, affiche une bannière d’incident et un lien vers les logs.

4.4 MetricsStrip
- Rôle: afficher la latence moyenne des flux (p50/p90), erreurs récentes (5m), rôle courant, statut transport (SSE/WS).
- Entrées:
  - metrics:tick (EVENTS v1) périodique OU calcul local (mesures de stream).
  - role: RBAC v1 (afficher rôle; pas de capability requise).
- Seuils (par défaut, ajustables):
  - Latence p90: ok < 2.0s, warn 2.0–3.5s, error > 3.5s.
  - Taux erreurs: ok < 1%, warn 1–3%, error > 3%.
- Exigences:
  - Aucune information sensible; lecture-only.

-----------------------------------------------------------------------

5) Schémas JSON (type-safe) — UI contracts v1

5.1 ChatRequest (POST /api/agents/{slug}/chat)
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ChatRequest v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["message"],
  "properties": {
    "message": { "type": "string", "minLength": 1, "maxLength": 2000 },
    "thread_id": { "type": "string" }
  }
}

5.2 ChatResponseAck
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ChatResponseAck v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["accepted", "correlation_id"],
  "properties": {
    "accepted": { "type": "boolean", "const": true },
    "correlation_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    }
  }
}

5.3 Host↔Widget postMessage Envelope
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Widget PostMessage Envelope v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["kind", "ts", "payload"],
  "properties": {
    "kind": {
      "type": "string",
      "enum": ["widget:init", "widget:context", "widget:ready", "widget:state"]
    },
    "ts": { "type": "string", "format": "date-time" },
    "payload": { "type": "object" },
    "correlation_id": {
      "type": "string",
      "pattern": "^[0-9a-fA-F-]{36}$"
    }
  }
}

5.4 UI Log Entry (front)
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UILogEntry v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["level", "ts", "component", "action", "correlation_id"],
  "properties": {
    "level": { "type": "string", "enum": ["debug", "info", "warn", "error"] },
    "ts": { "type": "string", "format": "date-time" },
    "component": { "type": "string" },
    "action": { "type": "string" },
    "actor": { "type": "object" },
    "agent": { "type": "string" },
    "thread_id": { "type": "string" },
    "correlation_id": { "type": "string" },
    "details": { "type": "object" }
  }
}

Nota: Les événements applicatifs utilisent les schémas d’EVENTS v1 (non répliqués ici).

-----------------------------------------------------------------------

6) Exemples (minimaux)

6.1 POST Chat → Ack
Request:
{
  "message": "ping cockpit",
  "thread_id": "th_abc"
}
Response:
{
  "accepted": true,
  "correlation_id": "f7aa97de-8c1b-4d97-8d0b-7d2a4cf14d4b"
}

6.2 Stream (EVENTS v1: chat:agent_stream, chunk 0)
{
  "type": "chat:agent_stream",
  "ts": "2025-10-13T06:29:40.612Z",
  "actor": { "id": "agent_jared", "kind": "agent", "role": "agent" },
  "thread_id": "th_abc",
  "correlation_id": "f7aa97de-8c1b-4d97-8d0b-7d2a4cf14d4b",
  "payload": { "chunk": "pong...", "index": 0, "done": false, "latency_ms": 285 }
}

6.3 WidgetHost Handshake
Host→Widget:
{
  "kind": "widget:init",
  "ts": "2025-10-13T06:29:45Z",
  "correlation_id": "42a1c9c3-6f3d-4d6d-b2e9-31e071b3c4f0",
  "payload": {
    "actor": { "id": "user_su_001", "role": "superuser" },
    "agent": "jared",
    "capabilities_allowed": ["read:metrics"]
  }
}
Widget→Host:
{
  "kind": "widget:ready",
  "ts": "2025-10-13T06:29:45Z",
  "correlation_id": "42a1c9c3-6f3d-4d6d-b2e9-31e071b3c4f0",
  "payload": {
    "version": "1.2.0",
    "capabilities_declared": ["read:metrics"]
  }
}

-----------------------------------------------------------------------

7) Contrôles & validations

- Conformité EVENTS v1:
  - ChatPanel émet `chat:user_message` (écho local) et consomme `chat:agent_stream`.
  - `correlation_id` obligatoire et stable pour la séquence POST→SSE/WS→logs.
- RBAC v1:
  - write:chat requis pour POST; viewer ne voit pas le ChatPanel (masqué ou disabled).
  - WidgetHost vérifie registry.scope (agent autorisé) et capabilities_declared ⊆ capabilities (deny-by-default pour write:*).
- Sécurité (SECURITY_BASELINES):
  - CSRF & session binding sur POST.
  - CSP stricte; pas d’inline/script noncé uniquement si nécessaire (éviter dans l’iframe).
  - postMessage filtré par origin (registry.origin) + schéma (enveloppe v1).
  - Anti-replay: horodatages raisonnables; idempotence via (correlation_id, thread_id, index).
- Observabilité:
  - Logs UI structurés avec correlation_id pour: submit chat, ack, stream connect/disconnect, widget mount/unmount.
  - Emission `widget:update` sur mount/unmount/state_changed (EVENTS v1).
- Tests (e2e requis Sprint 01):
  - superuser → cockpit {jared} → envoi message → réception stream (≥2 chunks, done) → widget factice mount() (read-only).

-----------------------------------------------------------------------

8) Compatibilité & versionnage

- COCKPIT_TEMPLATE v1:
  - Ajouts compatibles: nouveaux champs optionnels, nouveaux états UI non-destructifs, nouveaux messages postMessage optionnels.
  - Ruptures: changement sémantique des API ChatPanel/WidgetHost/MessageStream; nécessitent v2 et migration documentée.
- Rollback:
  - Les modifications sont enregistrées dans l’Append Log; retour à v-1 = revert + revalidation e2e pivot.

-----------------------------------------------------------------------

9) Risques sécurité (parano v1) & mitigations

- Évasion sandbox widget:
  - CSP stricte, origin allowlist, validation schéma postMessage, deny des messages inconnus.
- Escalade de privilèges via widget:
  - Deny-by-default write:*; vérification runtime capabilities; logs/audit mount; system:alert en cas d’abus.
- Mauvaise corrélation:
  - Middleware d’injection/propagation correlation_id; assertions e2e; refus de rendu stream sans correlation_id.
- CSRF/session hijacking:
  - SameSite cookies, X-CSRF-Token signé, session_fingerprint; tests négatifs e2e (échec attendu).
- Flaky transport:
  - backoff exponentiel + jitter, limites de retry; états reconnecting visibles; métriques de stabilité.

-----------------------------------------------------------------------

10) Notes d’implémentation (Nuxt 4 + Tailwind 4)

- Pages/Routes:
  - app/routes/cockpits/[agent_slug].vue (ou équivalent)
- State/composables:
  - useCorrelationId(), useStreamClient(SSE/WS), useRBAC(), useUILogger()
- Tailwind 4:
  - Utiliser classes utilitaires, focus-visible, aria-[state] pour états.
- A11y:
  - Shortcut Ctrl+Enter pour Chat; aria-live pour MessageStream.
- No console en prod:
  - Utiliser logger structuré; rediriger erreurs vers error:occurred (EVENTS v1) côté back si utile.

-----------------------------------------------------------------------

Append Log
- 2025-10-13 — Alice (Lead Orchestrator): Création initiale de la spécification COCKPIT_TEMPLATE v1 (layout, lifecycle, composants et contrats, sécurité, tests e2e, append log).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — widgets internes only (internalOnly), PostMessage strict (schéma + capability par message), Safe Mode documenté, référence CSP intégrée.
