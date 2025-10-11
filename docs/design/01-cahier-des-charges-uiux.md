## Standards UI/UX PixelProwlers

### Vision générale
- Interface Nuxt 4 sobre, inspirée d’un niveau de finition “Apple-grade”.
- Palette basée sur les tokens OKLCH définis dans `@/assets/css/main.css`.
- Mode sombre par défaut, bascule `useUserTheme()` respectant `prefers-color-scheme`.

### Grille & layout
- `AppShell` fournit header, toolbar, contenu, footer modulaires.
- Largeur de page limitée à `max-w-6xl`, marges fluides (4 → 8).
- Utiliser les helpers globaux (`u-grid-page`, `u-card`, `u-header`).

### Typographie & iconographie
- Fonte sans-serif système (`--font-sans`).
- Tailles : 12/14/16/20/24/32 selon hiérarchie. Toujours déclarer dans les styles des composants.
- Icônes décoratives avec texte accessible (`sr-only`) ou `aria-hidden="true"`.

### Couleurs & états
- `text-color-*` et `bg-color-*` pour textes et fonds.
- États interactifs : hover (+4% de luminosité), focus via `u-focus-ring`, active (scale légère / couleur).
- États critiques : `--color-danger`, `--color-warning`, `--color-success`.

### Motion & accessibilité
- Animations optionnelles, durée < 200 ms, respecter `prefers-reduced-motion`.
- Modals/Dialogs : focus trap via Radix-Vue, fermeture ESC + bouton explicite.
- Composants de formulaire : labels visibles, `aria-describedby` pour hints/erreurs.

### Sécurité & contenu
- Aucune donnée PII en placeholder.
- Contrôles côté serveur pour les appels sensibles (`ask-agents`).
- Prévoir champs honeypot invisibles (activés sprint suivant).
