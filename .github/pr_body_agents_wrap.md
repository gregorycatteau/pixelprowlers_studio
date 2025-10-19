# PR — Alignement contrat API /api/agents (wrap réponse)

## Résumé
- Aligne le backend avec le contrat consommé par le frontend Nuxt.
- Avant: `/api/agents/` renvoyait un tableau JSON `[]`.
- Après: `/api/agents/` renvoie un objet JSON `{ "agents": [...] }`.

Objectif: éviter les écarts de contrat et stabiliser l’intégration front/back.

---

## Contexte / Problème
Le handler Nuxt côté serveur (server/api/agents/index.get.ts) et les types (shared/types/agents.ts) s’attendent à une réponse de la forme:
```json
{ "agents": [ { "...": "..." } ] }
```
Le backend renvoyait `[]` (tableau pur). Cela peut provoquer des erreurs d’intégration (parsing/typing) et complexifie l’évolution du contrat public.

---

## Changements
- Modifie l’endpoint GET `/api/agents/` pour envelopper la liste d’agents:
  - Avant: `[]`
  - Après: `{ "agents": [] }`
- Aucune modification du contenu interne de chaque item (AgentSummary) ni des autres endpoints.

---

## Contrat API (avant / après)

Avant:
```json
[
  {
    "slug": "claire",
    "name": "Claire",
    "alias": "…",
    "remaining_eur_today": "2.50",
    "schema_version": "v1",
    "profile_version": "2025-10-01"
  }
]
```

Après:
```json
{
  "agents": [
    {
      "slug": "claire",
      "name": "Claire",
      "alias": "…",
      "remaining_eur_today": "2.50",
      "schema_version": "v1",
      "profile_version": "2025-10-01"
    }
  ]
}
```

---

## Impact (Front / Back)
- Front:
  - Le code et les types existants (AgentsResponse) attendaient déjà `{ agents: [...] }`; pas d’adaptation supplémentaire.
- Back:
  - Changement limité à la forme de la payload de réponse. Aucun changement de sécurité, permissions ou logique métier.

---

## Tests / Validation
- Local (dev):
  1) Démarrer le backend (Django).
  2) Appeler `GET /api/agents/` (navigateur/curl):
     - Curl: `curl -i http://localhost:8000/api/agents/`
  3) Vérifier qu’on obtient `{ "agents": [...] }` (HTTP 200).

- Front (Nuxt server route):
  1) Démarrer le front et appeler `/server/api/agents`.
  2) Vérifier l’absence d’erreur de parsing et la présence des agents via la route serveur.

- CI:
  - Lint/Type/Tests doivent passer (jobs Web/API).
  - Aucune régression attendue (changement de forme maîtrisé).

---

## DoD / Critères d’acceptation (G/W/T)
- Given un backend démarré
- When j’appelle `GET /api/agents/`
- Then la réponse est un objet JSON contenant la propriété `agents` de type tableau, avec les mêmes items qu’auparavant.

---

## Sécurité / Confidentialité
- Pas d’exposition de données sensibles.
- Réponse simplement enveloppée; pas d’impact sur l’authentification ni les permissions.

---

## Rollback
- Revenir à la réponse sous forme de tableau si besoin (non recommandé).
- Impact minimal; aucune migration.

---

## Liens
- Front handler (attente contrat): `frontend/server/api/agents/index.get.ts`
- Types front: `frontend/shared/types/agents.ts`
- Roadmap: `docs/roadmap/15_day_plan.md`
- PR S1 durcissement CI: #14

---
Veuillez cocher:
- [ ] Contrat appliqué et vérifié localement
- [ ] CI verte (Web/API)
- [ ] Aucun consumer externe affecté (contrat documenté)
