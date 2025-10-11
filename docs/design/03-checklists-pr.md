## Checklist composant UI
- [ ] Props typés, valeurs par défaut via `withDefaults`.
- [ ] Classes explicites + `@apply` dans `<style scoped>` (pas d’utilitaires dans le template).
- [ ] États : hover / focus (`u-focus-ring`) / active / disabled / loading couverts.
- [ ] A11y : rôle adapté, `aria-*` pertinents, textes cachés (`sr-only`) si icônes seules.
- [ ] Tests manuels : clavier (Tab, Shift+Tab), navigation screen reader de base.

## Checklist page / vue
- [ ] Page encapsulée dans `AppShell` avec slots header/toolbar/footer.
- [ ] Sections nommées (`page-section`, `page-grid`…) et usage de `PxCard`, `PxTable`, `PxModal`, etc.
- [ ] Données fictives neutres (pas de PII), contenu dynamique protégé (`try/catch`, erreurs gérées).
- [ ] Interaction Radix-Vue intégrée (Dialog/Popover/Toast) et fonctionnelle.
- [ ] Lighthouse desktop ≥ 95 (Perf, A11y, Best Practices) + capture jointe.

## Checklist A11y / Sécurité / Perf
- [ ] Labels visibles, `aria-describedby` pour hints/erreurs, messages d’erreur en clair.
- [ ] Focus trap vérifié pour modals, échappement via ESC + bouton close.
- [ ] Pas d’injection non contrôlée (`v-html` proscrit), logs limités à `console.info`.
- [ ] Budgets : LCP < 2.0 s, INP < 200 ms, CLS < 0.05 (mesure locale).
- [ ] Prévoir champ honeypot (commenté si non activé) pour formulaires publics.

## Definition of Done (rappel)
- [ ] Refacto conforme au cahier des charges UI/UX.
- [ ] Documentation mise à jour (`docs/design`).
- [ ] Rapports Lighthouse et budgets joints à la PR.
