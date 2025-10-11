## Guide de migration front (Sprint 0B)

### 1. Préparation
- Identifier la page legacy et lister sections/CTA/données critiques.
- Vérifier les dépendances côté serveur (API, middleware, auth).
- Créer un plan de découpe : composants globaux (`components/ui`) vs spécifiques page.

### 2. Structure Nuxt
- Encapsuler la page dans `AppShell` avec slots `header`, `toolbar`, `footer`.
- Utiliser `PxHeader` pour le haut de page et définir les actions du toolbar.
- Construire le layout en sections explicites (`page`, `page__section`, etc.).

### 3. Styling
- Bannir les utilitaires Tailwind dans le template ; utiliser `@apply` dans `<style scoped>`.
- S’appuyer sur les helpers (`u-card`, `u-grid-page`, `u-btn-base`) et sur les utilitaires personnalisés (`text-color-*`, `bg-color-*`).
- Partager les patterns réutilisables dans `components/ui` ou `components/<feature>/`.

### 4. Accessibilité & UX
- Labels visibles + `aria-describedby` pour formulaires (cf. `PxInput`).
- Gérer les messages d’erreur via `PxToast` ou zones `role="alert"`.
- Intégrer au moins une interaction Radix (Dialog/Popover) pour assurer focus trap.

### 5. Performance & QA
- Garder le DOM minimal, privilégier les slots.
- Vérifier l’absence de `console.log` permanents (hors instrumentation `console.info`).
- Exécuter Lighthouse (desktop) : Perf/A11y/Best ≥ 95, budget LCP < 2 s, INP < 200 ms, CLS < 0.05.

### 6. Livraison
- Mettre à jour les docs s’il y a de nouveaux patterns.
- Ajouter des entrées dans `03-checklists-pr.md` si nécessaire.
- Préparer captures Lighthouse (rapport + métriques budgétaires).
