# 08 — Mail, transport & DNS (e‑OTP)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Objectifs et exigences
2. Providers envisagés et architecture de transport
3. Fallback SMTP (sécurisé)
4. Politique DNS: SPF, DKIM, DMARC, MTA‑STS, TLSRPT
5. Délivrabilité, bounces et monitoring
6. Sécurité contenu e‑mail e‑OTP
7. Opérations: déploiement, validation et runbooks
8. Références internes
9. Points ouverts / TODO

1) Objectifs et exigences
- Assurer un envoi e‑mail fiable pour le code e‑OTP, avec délivrabilité contrôlée et sans fuite de données sensibles.
- Supporter deux modes:
  - Provider API (recommandé en prod) avec webhooks bounces.
  - Fallback SMTP (relais authentifié) en cas d’indisponibilité provider.
- Garantir une configuration DNS conforme (SPF/DKIM/DMARC) et du transport TLS renforcé (MTA‑STS/TLSRPT).
- Ne jamais logguer ni stocker de secret ou de code e‑OTP en clair.

2) Providers envisagés et architecture de transport
- Providers shortlist:
  - Postmark (simplicité, focus transactional, webhooks bounces clairs)
  - SendGrid (écosystème large, tuning fin, Webhooks Events)
- Architecture cible:
  - App (Django) → Mailer Abstraction (S2) → Provider API (HTTPS, clé API via secret manager)
  - Fallback: App → SMTP relay (TLS obligatoire, AUTH)
- Domaines/expéditeurs:
  - Domaine principal: pixelprowlers.io
  - Sous‑domaines dédiés (recommandé pour cloisonner réputation): mail.pixelprowlers.io ou notify.pixelprowlers.io
- Environnements:
  - dev/test: stub/local catcher (mailhog/mailpit) ou sandbox provider
  - stage/prod: provider réel avec quotas d’alarme et bounces monitorés
- Logs/metriques:
  - eotp_mail_send_total, eotp_mail_bounce_total{type,domain}, latence send (si API répond), sans PII

3) Fallback SMTP (sécurisé)
- Paramètres généraux:
  - STARTTLS/TLS requis, AUTH obligatoire, ciphers modernes
  - fail_silently=false en prod (pour remonter erreurs), true en dev (optionnel)
- Rotation des credentials:
  - Stockage dans secret manager, rotation périodique, accès minimal
- Circuit‑breaker:
  - Si taux d’échec envoi > seuil (ex. 5% sur 5 min): bascule contrôlée vers provider secondaire ou attente + alerte
- Journalisation:
  - Ne pas journaliser le contenu du message; seulement metadata non sensible (provider_id, status)

4) Politique DNS: SPF, DKIM, DMARC, MTA‑STS, TLSRPT
4.1. SPF
- Enregistrements TXT (exemple, à adapter selon provider choisi):
  - pixelprowlers.io TXT: v=spf1 include:postmarkapp.com include:sendgrid.net -all
  - Si sous‑domaine dédié (notify.pixelprowlers.io): v=spf1 include:postmarkapp.com -all
- Bonnes pratiques:
  - Éviter multiples includes non utilisés; limiter à providers réellement actifs
  - “-all” (hard fail) en prod; en phase d’observation, “~all” possible

4.2. DKIM
- Clés 2048 bits recommandées, un sélecteur par provider
  - postmark._domainkey.pixelprowlers.io TXT: “v=DKIM1; k=rsa; p=…”
  - s1._domainkey.pixelprowlers.io / s2._domainkey.pixelprowlers.io pour SendGrid
- Rotation:
  - Sélecteurs multiples (actif/standby), rotation programmée

4.3. DMARC
- Enregistrement TXT (niveaux progressifs):
  - Étape 1 (monitoring): _dmarc.pixelprowlers.io TXT: v=DMARC1; p=none; rua=mailto:dmarc-reports@pixelprowlers.io; ruf=mailto:dmarc-forensic@pixelprowlers.io; fo=1
  - Étape 2 (quarantaine): p=quarantine; pct=50
  - Étape 3 (rejet): p=reject; pct=100
- Rapport:
  - Mettre en place boîtes aux lettres dédiées/parseur pour rapports agrégés

4.4. MTA‑STS
- Fichier de politique (hébergé sur https://mta-sts.pixelprowlers.io/.well-known/mta-sts.txt):
  - mode: enforce
  - max_age: 86400
  - mx: mx1.pixelprowlers.io
- DNS (TXT):
  - _mta-sts.pixelprowlers.io TXT: v=STSv1; id=2025101701
- Avantage:
  - Force TLS valide côté transport inter‑MTA

4.5. TLSRPT
- DNS (TXT):
  - _smtp._tls.pixelprowlers.io TXT: v=TLSRPTv1; rua=mailto:tlsrpt@pixelprowlers.io
- Permet de recevoir rapports d’échecs TLS de transport

5) Délivrabilité, bounces et monitoring
- Bounces:
  - Hard: domaine inexistant, refus permanent
  - Soft: boîte pleine, transient
- Collecte:
  - Webhooks provider (recommandé) vers endpoint dédié (S2), stockage minimal (hash d’email, code, typologie)
  - En fallback: mailbox de retour analysée périodiquement
- Actions:
  - Taux de bounces par domaine/IP; geler resend pour destinataires présentant trop d’échecs consécutifs
- Listes:
  - Pas de liste blanche d’urgence pour e‑OTP (risque de spoof), préférer diagnostics/alertes
- Métriques:
  - eotp_mail_bounce_total{type,domain}, eotp_mail_send_total, ratio bounces/send
- Alertes (cf. 07):
  - WARN si hard bounce > 1%/h, CRIT > 3%/h par domaine/provider

6) Sécurité contenu e‑mail e‑OTP
- Contenu minimal:
  - Objet: “Votre code PixelProwlers”
  - Corps: “Votre code de vérification: 123456 (valide 3 minutes). Ne le partagez jamais.”
  - Aucune PII; pas de lien cliquable “de connexion” (limiter phishing)
  - Watermark anti‑phishing (texte statique, mention du domaine)
- Localisation:
  - FR (par défaut), extensible i18n
- Anti‑réutilisation:
  - Code invalidé côté serveur après consommation ou resend
- Tracking:
  - Désactiver balises de tracking; non nécessaires pour OTP

7) Opérations: déploiement, validation et runbooks
- Déploiement DNS:
  - Ordre: DKIM (public keys) → SPF → DMARC(p=none) → MTA‑STS/TLSRPT
  - Validation: dig/nslookup pour chaque enregistrement; outils provider pour DKIM pass
- Validation transport:
  - Test SMTP TLS (openssl s_client) — manuel/ops; en prod préférer tests synthétiques automatisés
  - Provider sandbox pour envs non prod
- Runbooks:
  - “Drop Délivrabilité”: vérifier SPF/DKIM pass, DMARC reports, statut provider, queue SMTP
  - “Spike bounces”: identifier domaines affectés, basculer provider si incident, ouvrir ticket postmaster si besoin
  - “Indispo provider”: activer fallback SMTP, réduire débit, alerter ops
- Sécurité secrets:
  - Clés API provider/SMTP dans secret manager; jamais en repo; rotation programmée

8) Références internes
- 02 — Architecture cible: ./02-architecture-cible.md
- 04 — Plan de sprints: ./04-plan-de-sprints.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md

9) Points ouverts / TODO
- Choisir provider primaire (Postmark vs SendGrid) et secondaire (si multi‑provider).
- Définir les sélecteurs DKIM et la politique de rotation (calendrier).
- Mettre en place boîtes tlsrpt@ et dmarc‑reports@ et leur traitement.
- Rédiger le endpoint Webhook bounces (S2) et le modèle minimal de stockage/metrics.
- Décider du sous‑domaine d’envoi (notify.pixelprowlers.io) vs domaine apex.
