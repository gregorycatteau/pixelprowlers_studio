# PixelProwlers Studio — Daily Log (Temps réel)

But
- Centraliser, en temps réel, l’avancement opérationnel du projet.
- Assurer des briefs cadencés à 08:00, 12:00, 16:00, 18:00, 20:00 (heure locale projet).
- Tracer décisions, risques, métriques et liens PR/Issues pour garantir la traçabilité.

Responsable
- Coordinatrice: Alice (@gregorycatteau)
- Source de vérité: ce fichier + PR/Issues liées
- Timezone: Europe/Paris (UTC+01/+02 selon saison)

Règles d’or
- Pas de secrets/PII dans les logs.
- Messages concis et actionnables.
- Lier systématiquement PR/Issues (ex: #14, #10).
- Statut CI/prod clair (verte/rouge/jaune + lien si pertinent).
- Utiliser les balises proposées ci-dessous (Areas/Agents/Phases).

Areas (balises)
- [sec] sécurité (Bandit/Gitleaks/headers)
- [ci] CI/CD (workflows, gates, audits deps)
- [back] backend (Django, API, OpenAPI)
- [front] frontend (Nuxt, UI, a11y, perf)
- [qa] QA (tests, coverage, e2e)
- [docs] docs/ADR/knowledge
- [analytics] events/privacy
- [infra] environnements/staging/prod

Agents (virtuels → owner réel)
- Alice, Bastien, Chloé, Diego, Élodie, Gaëlle, Farid, Inès, Jules
- Mapping: .github/owners.yml (actuellement → @gregorycatteau)

Phases
- S1: CI & hygiène
- S2: Sécurité
- S3: Qualité produit
- REL: Release readiness

Format — Entrée temps réel (one-liner)
[YYYY-MM-DD HH:MM] [area] [phase] [agent] — message court — refs: #PR/#issue — CI: état
Exemples:
- [2025-10-04 10:12] [ci] [S1] [Alice] — ruff/pytest.ini mergés en draft PR #14 — CI: jaune (npm audit bloquant ajouté)
- [2025-10-04 11:05] [sec] [S2] [Bastien] — bandit.yaml v1 (proposal) prêt — refs: #11 — CI: n/a

Format — Entrée détaillée (multi-lignes)
### [YYYY-MM-DD HH:MM] [area] [phase] [agent]
- Contexte:
- Fait:
- Prochain:
- Blocage/Risque:
- Réfs: #PR/#issue | Lien(s)
- CI: verte/jaune/rouge + motif

Briefs cadencés (08:00, 12:00, 16:00, 18:00, 20:00)
- Structure attendue:
  - FAIT (depuis dernier brief)
  - EN COURS (deltas jusqu’au prochain brief)
  - BLOCAGES/RISQUES (mitigation, besoin d’arbitrage)
  - DECISIONS/ADR (prises/à prendre)
  - CI/GATES (état synthèse)
  - ACTIONS (qui/quoi d’ici au prochain brief)
- Après chaque brief: poster un résumé court dans la PR “ops/collab” avec les points clés (copier/coller la section).

Liens utiles
- Roadmap (15 jours): docs/roadmap/15_day_plan.md
- Epics: S1 #10, S2 #11, S3 #12, REL #13
- PR S1 durcissement CI: #14
- RACI: docs/RACI.md
- Security: security/SECURITY.md
- CI: .github/workflows/

Commit suggéré
- docs(roadmap): update daily_log (Jx HH:MM brief)
- docs(roadmap): update daily_log (realtime)

---

## JOURNAL

### YYYY-MM-DD — Briefs programmés
- 08:00 — (à compléter)
- 12:00 — (à compléter)
- 16:00 — (à compléter)
- 18:00 — (à compléter)
- 20:00 — (à compléter)

Entrées temps réel
[YYYY-MM-DD HH:MM] [area] [phase] [agent] — message — refs — CI: état

---

## TEMPLATE — Brief (copier/coller)

### YYYY-MM-DD HH:MM — Brief [matin/midi/après-midi/soir] (Coord. @gregorycatteau)
- FAIT:
  - …
- EN COURS (jusqu’au prochain brief):
  - …
- BLOCAGES/RISQUES:
  - …
- DECISIONS/ADR:
  - …
- CI/GATES:
  - Web: …
  - API: …
  - Security/Scans: …
- ACTIONS (avant prochain brief):
  - …

---

## TEMPLATE — Entrée détaillée (multi-lignes)

### [YYYY-MM-DD HH:MM] [area] [phase] [agent]
- Contexte:
- Fait:
- Prochain:
- Blocage/Risque:
- Réfs:
- CI:

---

## TABLEAU ÉTAT CI (optionnel à maintenir 1×/jour)

| Date       | Web CI | API CI | Security Scans | Coverage Back | Coverage Front | Notes |
|------------|--------|--------|----------------|---------------|----------------|-------|
| YYYY-MM-DD |        |        |                |               |                |       |

---

## LISTE DECISIONS/ADR (journal)

- [YYYY-MM-DD HH:MM] Décision: … — Réfs: #PR/#issue — ADR: docs/adr/…
- [YYYY-MM-DD HH:MM] Décision: … — …

---

## RISQUES (actifs) & MITIGATIONS

- [YYYY-MM-DD] Risque: … — Impact: … — Probabilité: … — Mitigation: … — Owner: …
- …

---

## RÈGLES DE TENUE DU LOG

- Chaque entrée doit commencer par un timestamp [YYYY-MM-DD HH:MM].
- Lier les éléments (PR/Issues) quand c’est pertinent.
- S’interdire secrets/PII; préférer “voir variable d’env”/“voir secret GitHub”.
- Si un brief programmé est manqué, rattrapage au prochain slot avec récapitulatif.
- En cas d’incident, consigner immédiatement une entrée “Incident” puis ouvrir une issue/ADR si nécessaire.

Fin du document.
