# POSTMARK_DNS — Guide “copier‑coller” (S2)
Status: READY (templates sans secrets)
Auteur: Cline
Date: 2025‑10‑17

Objectif
- Activer l’envoi réel e‑mail e‑OTP via Postmark pour le domaine/sous‑domaine dédié.
- Fournir des enregistrements DNS “copier‑coller” (SPF, DKIM 2048, Return‑Path), DMARC (phase‑in), MTA‑STS (enforce) et TLSRPT.
- Aucune donnée sensible dans ce document.

Domaine(s) recommandés
- Domaine principal: pixelprowlers.io
- Sous‑domaine d’envoi DÉDIÉ (fortement recommandé): notify.pixelprowlers.io
  - Cloisonne la réputation expéditeur et simplifie la rotation DMARC/DKIM.

1) SPF (TXT)
- Domaine apex (si envoi depuis l’apex):
  Name: pixelprowlers.io
  Type: TXT
  Value: v=spf1 include:postmarkapp.com -all
- Sous‑domaine dédié (recommandé):
  Name: notify.pixelprowlers.io
  Type: TXT
  Value: v=spf1 include:postmarkapp.com -all
Notes:
- Utiliser “-all” en prod. Pendant la phase d’observation initiale, “~all” est acceptable, puis passer en “-all”.

2) DKIM 2048 (TXT)
- Clé publique DKIM fournie par Postmark (copier la valeur “p=…” depuis l’interface).
  Name: pm._domainkey.notify.pixelprowlers.io
  Type: TXT
  Value: v=DKIM1; k=rsa; p=REPLACE_WITH_POSTMARK_DKIM_PUBKEY_2048

Rotation (recommandée semestrielle):
- Préparer un 2e sélecteur (ex: pm2._domainkey.notify.pixelprowlers.io) en “standby”.
- Basculer le sélecteur actif côté Postmark, puis retirer l’ancien après propagation (≥ 48h).

3) Return‑Path / Return‑MX Postmark (CNAME)
- Postmark requiert un sous‑domaine “bounce” pointant vers pm.mtasv.net pour le Return‑Path.
  Name: pm-bounces.notify.pixelprowlers.io
  Type: CNAME
  Value: pm.mtasv.net

4) DMARC (TXT) — phase‑in en 3 étapes
Étape 1 (monitoring):
- Name: _dmarc.notify.pixelprowlers.io
  Type: TXT
  Value: v=DMARC1; p=none; rua=mailto:dmarc-reports@pixelprowlers.io; ruf=mailto:dmarc-forensic@pixelprowlers.io; fo=1; sp=none; adkim=s; aspf=s

Étape 2 (quarantaine 50%):
- v=DMARC1; p=quarantine; pct=50; rua=mailto:dmarc-reports@pixelprowlers.io; ruf=mailto:dmarc-forensic@pixelprowlers.io; fo=1; sp=quarantine; adkim=s; aspf=s

Étape 3 (rejet 100%):
- v=DMARC1; p=reject; pct=100; rua=mailto:dmarc-reports@pixelprowlers.io; ruf=mailto:dmarc-forensic@pixelprowlers.io; fo=1; sp=reject; adkim=s; aspf=s

Règle d’escalade:
- Passer de none → quarantine → reject quand hard bounces < 1% sur 7 jours.

5) MTA‑STS (TXT + policy HTTPS)
- TXT version/id:
  Name: _mta-sts.notify.pixelprowlers.io
  Type: TXT
  Value: v=STSv1; id=2025101701
- Policy HTTPS (servie via TLS valide):
  URL: https://mta-sts.notify.pixelprowlers.io/.well-known/mta-sts.txt
  Contenu (exemple strict):
  mode: enforce
  max_age: 604800
  mx: mx1.pixelprowlers.io

6) TLSRPT (TXT)
- Name: _smtp._tls.notify.pixelprowlers.io
  Type: TXT
  Value: v=TLSRPTv1; rua=mailto:tlsrpt@pixelprowlers.io

7) Checklist d’activation (Ops)
- [ ] Ajouter/propager SPF, DKIM, CNAME pm-bounces (TTL 300–600).
- [ ] Publier MTA‑STS policy (fichier sur mta-sts.notify.pixelprowlers.io).
- [ ] Publier TLSRPT TXT, créer boîtes mail tlsrpt@ et dmarc-reports@ (routing + parsing de base).
- [ ] Activer le domaine/sender dans Postmark; vérifier “DKIM: pass”, “Return‑Path: verified”.
- [ ] Démarrer DMARC en p=none (monitoring), basculer selon bounces (< 1%/7j).

8) Validation rapide (exemples)
- dig TXT notify.pixelprowlers.io
- dig TXT pm._domainkey.notify.pixelprowlers.io
- dig CNAME pm-bounces.notify.pixelprowlers.io
- dig TXT _dmarc.notify.pixelprowlers.io
- dig TXT _mta-sts.notify.pixelprowlers.io
- dig TXT _smtp._tls.notify.pixelprowlers.io
- curl -s https://mta-sts.notify.pixelprowlers.io/.well-known/mta-sts.txt

9) Sécurité & bonnes pratiques
- Pas de secrets en DNS (clefs privés, tokens).
- DKIM 2048 bits, sélecteur unique actif + un sélecteur de rotation.
- DMARC “s” (strict alignment) recommandé: adkim=s, aspf=s.
- Maintenir “MAIL_FROM=security@pixelprowlers.io” (ou sous‑domaine) pour uniformité et anti‑phishing.
- Ne pas insérer de tracking pixel dans les e‑mails e‑OTP.

Annexe — Variables backend (.env)
- MAILER_PROVIDER=postmark | smtp | disabled
- MAIL_FROM=security@pixelprowlers.io
- POSTMARK_API_TOKEN=… (secret manager)
- POSTMARK_FROM=${MAIL_FROM}
- POSTMARK_WEBHOOK_SECRET=… (secret manager)
- EOTP_DISABLE_HMAC_FALLBACK=1 en prod (désactive fallback HMAC OTP)
