# 09 — UX spec e‑OTP (maquettes textuelles, ergonomie, a11y)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Principes UX
2. Parcours utilisateur (séquence)
3. Maquettes textuelles (wireframes)
4. États, erreurs et messages
5. Comportements (timers, resend, focus)
6. Accessibilité (a11y) et confort d’usage
7. Responsif & internationalisation
8. Testabilité (unit/E2E) et instrumentation
9. Références internes
10. Points ouverts / TODO

1) Principes UX
- Simplicité: concentrer l’attention sur la saisie du code (friction minimale).
- Clarté: messages explicites et non techniques; éviter toute fuite d’état sensible (invalid/expired → message générique côté UI).
- Prévisibilité: retour visuel immédiat (focus, validation locale), timers visibles pour TTL et cooldown resend.
- Sécurité perçue: conseils brefs (“Ne partagez jamais ce code.”), pas de lien de connexion dans l’e‑mail.

2) Parcours utilisateur (séquence)
- Étape 1 — Login (username/password)
  - Soumission → décision backend = “pending_2fa” → redirection /login/2fa.
- Étape 2 — Vérification e‑OTP (page /login/2fa)
  - Saisie du code (6 ou 8 chiffres).
  - Bouton “Continuer”.
  - Timer “Code valide X:YY” (TTL).
  - Lien/bouton “Renvoyer” (désactivé si cooldown).
- Étape 3 — Succès
  - Redirection /gate puis /console (ou destination du realm).
- Étape 4 — Échecs
  - Code invalide/expiré → message générique, possibilité de ressaisir / renvoyer après cooldown.
  - Verrouillage (trop d’essais) → message explicite + délai.

3) Maquettes textuelles (wireframes)
3.1. /login
- H1: “Démarrer une session”
- Form:
  - Label “Identifiant”
  - Input #username (text, autocomplete=username)
  - Label “Mot de passe”
  - Input #password (password, autocomplete=current-password)
  - Button (primary): “Continuer”
- Footer: lien vers mentions, accessibilité

3.2. /login/2fa
- H1: “Vérification à deux facteurs”
- Subtext: “Un code a été envoyé à votre adresse e‑mail.”
- Region (live polite): feedback messages
- Code input:
  - Variante A (un seul champ) — Input #code (inputmode=numeric, pattern="\\d*", maxlength=6|8)
  - Variante B (6 cases) — 6 inputs .otp-cell (tab/auto‑focus; a11y role group)
- Timer:
  - “Code valide encore 02:59”
- Actions:
  - Button (primary): “Continuer”
  - Button/link (secondary): “Renvoyer le code”
    - Tooltip/inline: “Disponible dans 00:28” (si cooldown)
- Aide:
  - “Ne partagez jamais ce code. Si vous n’avez rien reçu, vérifiez votre dossier indésirables.”

4) États, erreurs et messages
- idle: page affichée, #code vide, bouton primaire disabled tant que longueur non atteinte.
- typing: normalisation digits‑only, espaces ignorés, coller autorisé (filtré).
- submitting: spinner sur bouton, empêcher double‑submit.
- success: validation → redirection.
- errors (UI):
  - invalid_code (401/400): “Code invalide. Veuillez réessayer.”
  - expired: même message générique côté UI; inviter à renvoyer le code.
  - locked: “Trop de tentatives. Réessayez dans X minutes.”
  - rate_limited (429): “Trop de demandes. Réessayez dans X secondes.” (lire Retry‑After).
  - csrf_failed (403): flux de retry piloté par fetch‑auth (déjà implémenté).
- resend:
  - cooldown actif: bouton disabled, affichage countdown
  - quota dépassé: message “Limite de renvoi atteinte. Réessayez plus tard.”

5) Comportements (timers, resend, focus)
- Timer TTL:
  - Démarre à l’arrivée sur /login/2fa (valeur côté backend ou par défaut 3:00).
  - À 0: afficher “Code expiré” (subtext) + activer “Renvoyer”.
- Resend:
  - Au clic: POST resend, si 200 → message “Nouveau code envoyé”; si 429 → lire Retry‑After et démarrer cooldown.
  - Après resend: invalider localement le code actuel (vider #code).
- Focus:
  - Auto‑focus sur #code à l’ouverture.
  - Si 6 cases, avance/recul sur saisie/suppression; coller 6/8 chiffres préremplit.
- Prévention double‑soumission:
  - Désactiver bouton pendant requête / afficher spinner.

6) Accessibilité (a11y) et confort d’usage
- Contrastes AA, taille police ≥ 14px, taille cible tactile ≥ 44×44.
- Labels explicites (aria‑label si nécessaire), description d’erreurs via aria‑live="polite".
- Navigation clavier complète; ordre de tabulation logique.
- Annonces screen reader:
  - À l’arrivée, lire H1; lors d’erreurs, annoncer le message (region live).
  - Pour 6 cases OTP, regrouper avec role="group" + aria‑label “Code de vérification”.
- Langue: attr lang="fr" par défaut; locales extensibles.

7) Responsif & internationalisation
- Mobile‑first:
  - Afficher un seul champ #code sur < 640px; espacement généreux; bouton ancré bas.
- Desktop:
  - Layout centré, largeur max 480px.
- i18n:
  - Tous les messages externalisés; longueurs variables respectées (ex: en, es).
- Formats:
  - Heure/minute : MM:SS; séparateur “:” internationalisable.

8) Testabilité (unit/E2E) et instrumentation
- Unit/Vitest:
  - CodeInput: normalisation, coller, focus management, émission d’événement submit quand longueur atteinte.
  - Timer: faux timers, callbacks onExpire.
  - ResendButton: lecture Retry‑After, états disabled/enabled, compte à rebours.
- E2E/Playwright:
  - Happy path (existant): login → /login/2fa → peek → submit → /gate.
  - Invalid, expired, resend cooldown/quota, locked (messages et comportements).
  - Accessibilité basique: rôles/labels présents; navigation clavier.
- Instrumentation:
  - Ajouter data‑testid sur éléments clés (#code, btn-continue, btn-resend, ttl, msg).
  - Logs front (niveau debug) désactivés en prod; pas de PII.

9) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 03 — Threat model: ./03-threat-model.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail & DNS: ./08-mail-transport-et-dns.md

10) Points ouverts / TODO
- Décider entre champ unique vs 6 cases pour OTP (préférence: champ unique mobile‑first).
- Déterminer longueur code (6 vs 8) et impacts ergonomiques.
- Valider wording final (UX writing) et tonalité (vous/vous‑politesse).
- Décider support mode sombre (thème) et contrastes renforcés.
- Définir policy d’auto‑submit (soumission auto à longueur atteinte ou sur bouton seulement).
