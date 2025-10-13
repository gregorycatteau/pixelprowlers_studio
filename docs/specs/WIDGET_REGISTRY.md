# WIDGET_REGISTRY — Contrat, Schémas, Exemples, Gouvernance et Sécurité (v1)

Priorité stricte: Sécurité > Cohérence/Traçabilité > Ergonomie > Design
Références: EVENTS v1, RBAC v1, SECURITY_BASELINES, COCKPIT_TEMPLATE v1, GOVERNANCE v1

Cette spécification définit le registre global des widgets (fichier: widget_registry.json), son contrat, ses schémas de validation, ainsi que les processus de gouvernance et les garde-fous de sécurité. Le registre permet au Cockpit (Nuxt 4 + Tailwind 4) et au WidgetHost d’identifier, contrôler et monter des widgets dans un environnement sandboxé, avec un modèle de permissions explicites et “deny-by-default”.

---

## 1) Objet & portée

- Définir un registre unique des widgets, versionné et validé par schéma, afin de:
  - Déclarer l’identité d’un widget (id, version semver, owner).
  - Lister ses capacités (capabilities) explicites et ses dépendances (deps).
  - Limiter sa portée de montage (scope) à des agents spécifiques.
  - Publier son statut de maturité (alpha|beta|stable).
- Exclu (v1):
  - Définition des micro-permissions internes au widget (au-delà des capabilities globales).
  - Détails d’implémentation UI (style, props, etc.) — couverts par COCKPIT_TEMPLATE v1.

---

## 2) Format du registre

Fichier: widget_registry.json
Structure v1: un tableau d’entrées (une par widget “versionnée”). Chaque entrée est immuable (append-only); un nouveau changement fonctionnel crée une nouvelle entrée avec un nouveau semver.

- Recommandation d’organisation:
  - Un widget = un “id” stable.
  - Chaque version compatible = une nouvelle entrée avec le même “id” et “version” semver différente.
  - L’historique est donc conservé et diff-ables.

Optionnel: un objet enveloppe (registry) est possible à l’avenir (v2). En v1, on utilise un tableau plat.

---

## 3) Contrat (champs obligatoires et optionnels)

Champs obligatoires (v1):
- id: string — identifiant canonique global du widget (stable).
- version: string (semver) — ex: “1.2.3”.
- capabilities: array&lt;string&gt; — ex: [“read:metrics”, “emit:chat”]. Aucune capability write:* par défaut.
- deps: array&lt;string&gt; — ex: [“context:cdn@>=1.1”] (notation libre, voir contraintes).
- owner: string — slug d’un agent interne (registre interne) propriétaire/mainteneur (ex: “jared”, “talia”).
- scope: array&lt;string&gt; — liste des agent slugs autorisés à monter ce widget (deny-by-default pour les autres).
- status: enum — “alpha” | “beta” | “stable”.
- internalOnly: true — widgets internes uniquement (v1); aucune origin/URL externe autorisée.

Champs optionnels utiles (v1):
- title: string — nom lisible (UI).
- description: string — usage/documentation brève.
- entry_url: string — URL (même origine ou CDN autorisé) pour le bundle (montage iframe/sandbox).
- integrity: string — SRI (Subresource Integrity), ex: “sha256-…”.
- origin: string — origin autorisée pour postMessage (ex: “https://cdn.example.com”).
- csp: object — contraintes CSP à appliquer à l’iframe (renforcées par défaut côté host).
- tags: array<string> — catégorisation libre (ex: [“metrics”, “observability”]).

Nota sécurité: “entry_url”, “origin”, “integrity”, “csp” sont optionnels mais fortement recommandés si un bundle externe est chargé.

---

## 4) Schéma JSON (jsonschema draft 2020-12)

Schéma d’une entrée de widget (single entry):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pixelprowlers.local/schemas/widget.entry.v1.json",
  "title": "Widget Registry Entry v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "version", "capabilities", "deps", "owner", "scope", "status", "internalOnly"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_\\-]{2,63}$"
    },
    "version": {
      "type": "string",
      "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
    },
    "capabilities": {
      "type": "array",
      "minItems": 1,
      "maxItems": 100,
      "items": {
        "type": "string",
        "pattern": "^(read|emit|write|manage):[a-z][a-z0-9_:-]*$"
      }
    },
    "deps": {
      "type": "array",
      "maxItems": 50,
      "items": {
        "type": "string",
        "pattern": "^[a-z][a-z0-9_\\-]*:[a-z][a-z0-9_\\-]*@[^\\s]+$"
      }
    },
    "owner": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9_\\-]{2,63}$"
    },
    "scope": {
      "type": "array",
      "minItems": 1,
      "maxItems": 1000,
      "uniqueItems": true,
      "items": {
        "type": "string",
        "pattern": "^[a-z][a-z0-9_\\-]{2,63}$"
      }
    },
    "status": {
      "type": "string",
      "enum": ["alpha", "beta", "stable"]
    },
    "internalOnly": { "type": "boolean", "const": true },
    "title": { "type": "string", "maxLength": 200 },
    "description": { "type": "string", "maxLength": 2000 },
    "entry_url": {
      "type": "string",
      "pattern": "^(?![a-zA-Z][a-zA-Z0-9+.-]*://).+"
    },
    "integrity": {
      "type": "string",
      "pattern": "^(sha(256|384|512))-([A-Za-z0-9+/=]+)$"
    },
    "origin": {
      "type": "string",
      "enum": ["self"]
    },
    "csp": {
      "type": "object",
      "additionalProperties": {
        "type": "string"
      }
    },
    "tags": {
      "type": "array",
      "maxItems": 50,
      "items": {
        "type": "string",
        "pattern": "^[a-zA-Z0-9_\\-]{1,32}$"
      }
    }
  },
  "allOf": [
    {
      "not": {
        "properties": {
          "capabilities": {
            "contains": { "type": "string", "pattern": "^write:" }
          }
        }
      }
    }
  ]
}
```

Schéma du registre (array d’entrées):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pixelprowlers.local/schemas/widget.registry.v1.json",
  "title": "Widget Registry v1",
  "type": "array",
  "items": { "$ref": "https://pixelprowlers.local/schemas/widget.entry.v1.json" },
  "maxItems": 10000,
  "uniqueItems": false
}
```

Remarques:
- Le “not … contains write:” implémente le deny-by-default pour write:*. Toute utilisation de write:* exige une dérogation formelle (voir Gouvernance).
- Le pattern des capabilities autorise read:*, emit:* par défaut. manage:* et write:* sont réservés (gouvernance renforcée).
- “deps” suit la notation libre “namespace:name@specifier” (ex: “context:cdn@>=1.1”, “api:metrics@~2.0”).

---

## 5) Exemples

- Exemple minimal (read-only, interne only):

```json
[
  {
    "id": "metrics_strip",
    "version": "1.2.0",
    "capabilities": ["read:metrics"],
    "deps": ["context:cdn@>=1.1"],
    "owner": "talia",
    "scope": ["talia", "bruce", "rand"],
    "status": "beta",
    "internalOnly": true,
    "title": "Metrics Strip",
    "description": "Affiche latence moyenne, erreurs récentes et statut transport.",
    "entry_url": "/widgets/metrics_strip/1.2.0/index.html",
    "integrity": "sha256-ZXhhbXBsZVNSSUJhc2U2NA==",
    "origin": "self",
    "csp": {
      "default-src": "'none'",
      "script-src": "'self'",
      "style-src": "'self'",
      "img-src": "'self'",
      "connect-src": "https://api.pixelprowlers.local",
      "frame-ancestors": "'none'"
    },
    "tags": ["metrics", "observability"]
  }
]
```

- Exemple avec capability d’émission contrôlée (interne only):

```json
[
  {
    "id": "chat_helper",
    "version": "0.9.1",
    "capabilities": ["read:metrics", "emit:chat"],
    "deps": ["context:cdn@>=1.1", "api:chat@^1.0"],
    "owner": "jared",
    "scope": ["jared"],
    "status": "alpha",
    "internalOnly": true,
    "title": "Chat Helper",
    "description": "Permet de déclencher des prompts de routine via le flux chat.",
    "entry_url": "/widgets/chat_helper/0.9.1/index.html",
    "origin": "self",
    "tags": ["chat"]
  }
]
```

Tentative refusée (write:* interdit par défaut — validation échoue):

```json
[
  {
    "id": "danger_widget",
    "version": "1.0.0",
    "capabilities": ["write:system"],
    "deps": [],
    "owner": "ops",
    "scope": ["talia"],
    "status": "alpha"
  }
]
```

---

## 6) Contrôles & validations

- Validation par schéma:
  - Chaque entrée doit valider `widget.entry.v1.json`.
  - Le registre (array) doit valider `widget.registry.v1.json`.
- Unicité logique recommandée:
  - (id, version) ne doit pas être dupliqué dans le registre.
- Intégrité opérationnelle:
  - Si “entry_url” et “integrity” sont fournis, WidgetHost vérifie SRI avant montage.
  - “origin” filtre les postMessage (allowlist) côté host.
- Conformité RBAC/Policy:
  - “scope” contraint le montage à la liste des agent slugs autorisés.
  - “owner” doit être un agent interne existant; sinon, l’entrée est rejetée.
  - Toute capability “emit:*” sera contrôlée par RBAC v1 à l’exécution.
- Deny-by-default:
  - write:* et manage:* ne sont pas autorisés en v1 sans dérogation (voir Gouvernance).
- Traçabilité:
  - Tout mount/unmount génère `widget:update` (EVENTS v1) + logs corrélés (correlation_id).

---

## 7) Gouvernance (processus)

- Ajout/modification d’un widget:
  1) Proposer une PR modifiant widget_registry.json (append-only, ne pas réécrire l’historique).
  2) Fournir:
     - Description de la finalité, owner, scope, capabilities.
     - Éventuelles preuves SRI, origin, et CSP suggérée.
     - Risques évalués (voir section Sécurité).
  3) CI:
     - Validation jsonschema (entries + registre).
     - Lint de conventions (id/slug, semver, uniqueness (id,version)).
  4) Revue SecOps obligatoire si capabilities incluent emit:* (ou toute capability sensible).
  5) Gate sécurité:
     - Aucune capability write:* ni manage:* acceptée par défaut en v1.
     - Exceptions: RFC sécurité, plan de tests négatifs, revues multi-signataires.
  6) Merge:
     - Tag de version documentaire (Append Log + changelog).
- Versionnage:
  - Nouveau comportement → bump semver (minor/major).
  - Breaking change → major (et entrée distincte).
- Dépréciation & retrait:
  - Marquer “deprecated” n’existe pas en v1: utiliser communication/roadmap + cesser d’utiliser les versions anciennes (mais conserver l’historique).
- Rollback:
  - Revert de commit + relance CI + revalidation e2e concernés.

---

## 8) Sécurité (gates et menaces)

- Menaces:
  - Exécution non autorisée (montage hors “scope”).
  - Évasion sandbox (CSP insuffisante, postMessage non filtré).
  - Escalade de privilèges via capabilities trop larges (ex: emit:* abusif).
  - Supply chain (bundle compromis, integrity manquante).
  - Fuite de données (widget exfiltrant via connect-src).
- Atténuations:
  - Deny-by-default: aucune action write:*; emit:* sous revue SecOps + RBAC runtime.
  - Sandbox iframe + CSP stricte par défaut (host) et CSP additionnelle par widget (optionnel).
  - Allowlist “origin” pour postMessage; validation de schémas des messages.
  - SRI (integrity) obligatoire pour bundles externes en prod; contrôles de signature/attestation quand disponible.
  - Journalisation corrélée (mount/unmount/state_changed): hash_prev/hash_curr dans les journaux d’audit.
  - Rate limiting/backpressure sur canaux d’émission du widget (emit:*).
  - Vérification “scope” au mount: si actor/agent ∉ scope → rejet + system:alert.
- Gates de promotion:
  - Aucune entrée avec write:* ou manage:* sans RFC approuvée + tests; sinon rejet CI.
  - CI: internalOnly doit être présent et égal à true; entry_url/origin ne doivent contenir aucun schéma externe (pas de "://").
  - Tests e2e cockpit: mount widget factice read-only; aucune action write possible.
  - Zéro violation CSP au montage (console propre en mode strict).

---

## 9) Intégration avec EVENTS v1 et WidgetHost

- Montage:
  - À mount(), émettre `widget:update` avec action=“mount”, capabilities et version déclarées.
  - Vérifier RBAC: le rôle courant doit permettre le montage et l’usage des capabilities read/emit déclarées.
- Cycle de vie:
  - idle → connecting → ready → error → reconnecting (COCKPIT_TEMPLATE v1).
  - À unmount(), émettre `widget:update` avec action=“unmount”.
  - En cas de changement d’état, `widget:update` action=“state_changed”.
- Corrélation:
  - Propager `correlation_id` depuis l’action UI déclenchant le mount.
  - Tous les événements et logs (front/back) associés doivent inclure `correlation_id`.

---

## 10) Qualité & Tests

- Tests de schéma (unitaires):
  - Valider tous les exemples canoniques; refuser write:* par défaut.
- Tests d’intégration:
  - Simulation mount() sur un agent autorisé vs non autorisé.
  - Vérifier que WidgetHost bloque tout postMessage non conforme et tout connect-src non autorisé.
- e2e (Playwright):
  - Sprint 01: chat + mount widget factice read-only; aucune action write (attendu: pass).
- Oracles:
  - Aucun événement `widget:update` sans fields communs EVENTS v1.
  - Journalisation structurée avec chaînage de hash.

---

## 11) Compatibilité & versionnage (registre)

- v1 du contrat:
  - Ajouts compatibles: champs optionnels (title, description, entry_url, integrity, origin, csp, tags).
  - Modifs breaking: changements de sémantique des champs obligatoires → v2.
- Migration:
  - Conserver les anciennes entrées (append-only); cockpit peut sélectionner la version la plus récente stable compatible.
- Rollback documentaire:
  - Toute modification est inscrite en “Append Log”.
  - Retour à v-1 = revert Git + revalidation CI + relance e2e pivot.

---

## 12) Références croisées

- docs/specs/EVENTS_v1.md — `widget:update` (mount|unmount|state_changed), champs communs et `correlation_id`.
- docs/specs/RBAC_v1.md — rôles, capabilities, deny-by-default; matrice d’accès.
- docs/specs/SECURITY_BASELINES.md — CSRF, session binding, nonce anti-replay, logs hashés, CSP.
- docs/specs/COCKPIT_TEMPLATE_v1.md — WidgetHost API: mount(), unmount(), loadContext().
- docs/roadmaps/Sprint_01_Cockpit_Template.md — scénarios e2e et gates de promotion.

---

## Append Log

- 2025-10-13 — Alice (Lead Orchestrator): Création initiale du WIDGET_REGISTRY v1 (contrat, schémas JSON, exemples, gouvernance, sécurité, intégration EVENTS/WidgetHost, plan de tests, rollback).
- 2025-10-13 — Alice (Lead Orchestrator): Patch durcissement v1 — internalOnly requis (true), URL/origin externes refusées, owner interne obligatoire, schémas mis à jour (entry_url sans schéma, origin="self"), exemples corrigés, gate CI ajouté.
