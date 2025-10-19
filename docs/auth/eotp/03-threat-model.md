# 03 — Threat model e‑OTP (sécurité par conception)
Status: DRAFT
Date: 2025-10-17
Auteur: Cline (Analyste/Architecte + SRE)
Version: 0.1

Table des matières
1. Portée et hypothèses
2. Actifs à protéger
3. Acteurs et menaces
4. Surfaces d’attaque (Django, Nuxt, Email, Redis, Réseau)
5. Scénarios d’attaque (STRIDE) et contre‑mesures
6. Politique de secrets et journalisation
7. Throttling & anti‑abus sans Turnstile
8. Politique resend & bounces
9. Vérification de contexte (session/UA/IP)
10. Données à caractère personnel (PII) et conformité
11. Plan de tests d’intrusion ciblés (Sprint 7)
12. Références internes
13. Points ouverts / TODO

1) Portée et hypothèses
- Portée: Tunnel e‑OTP (login → pending_2fa → verify/resend), proxies Nuxt → Django, stockage de challenge, envoi email, observabilité, rate‑limits.
- Hypothèses:
  - Pas de Turnstile/CAPTCHA (contraintes produit).
  - Canaux chiffrés (TLS) côté clients et inter‑services.
  - Secrets d’infra (pepper, SMTP creds) fournis par env/secret manager (non en repo).
  - Redis disponible en prod (ratelimits/nonce); fallback cache en dev/test.

2) Actifs à protéger
- Identité utilisateur (session Django, JWT éventuels).
- Secrets e‑OTP (code utilisateur court et secret 128 bits interne).
- Pepper e‑OTP et paramètres Argon2id.
- Métadonnées de contexte (UA hash, IP prefix).
- Journaux/événements (sans fuite de secrets ni d’emails en clair).
- Disponibilité des endpoints /api/auth/* (prévenir DoS, épuisement).

3) Acteurs et menaces
- Attaquant réseau (MITM limité par TLS; tente le rejeu, brute‑force OTP, IP rotation).
- Attaquant applicatif (forging de requêtes, contournement CSRF/nonce, replay de nonce).
- Utilisateur malveillant (resend spammable, enumeration d’utilisateurs).
- Attaquant mail (phishing, spoofing, interception boîte mail compromise, bounces storm).
- Insider limité (observabilité/logs: risque de fuite si mal configuré).

4) Surfaces d’attaque (Django, Nuxt, Email, Redis, Réseau)
- Backend Django:
  - /api/auth/login/, /api/auth/2fa/email/verify|resend, (test‑only) _peek.
  - CSRF, sessions cookies (Secure/SameSite), ratelimits DRF/Redis.
- Frontend/Nuxt:
  - Proxies server API vers Django; ajout X‑CSRFToken/X‑Request‑Nonce; gestion Retry‑After.
  - UI /login/2fa (normalisation, timers, erreurs).
- Email:
  - Transport SMTP/API; DNS expéditeur (SPF/DKIM/DMARC, MTA‑STS/TLSRPT).
- Redis:
  - Stores ratelimit/nonce; isolation réseau; auth; visibilité des clés (no PII en clair).
- Réseau:
  - Reverse proxy; X‑Request‑ID; entêtes de sécurité (CSP, X‑Frame‑Options, Referrer‑Policy, HSTS).

5) Scénarios d’attaque (STRIDE) et contre‑mesures
- S (Spoofing)
  - Usurpation session via cookie volé: cookies Secure/HttpOnly/SameSite, rotation/session invalidation à logout; forward_auth strict côté proxy; SameSite=Lax/Strict par realm.
  - Spoof email d’expéditeur: SPF/DKIM/DMARC “reject/quarantine”, MTA‑STS; pas de liens cliquables “sensibles” dans l’email OTP (réduire phishing).
- T (Tampering)
  - Altération OTP en transit: TLS end‑to‑end; comparaison constant‑time; OTP jamais loggé.
  - Manipulation Redis (keys): ACL Redis, réseau privé, AUTH, alerting sur keys pattern.
- R (Repudiation)
  - Négation d’action: journalisation signée/chaînée (hash chain) des events auth:eotp_* (prévu Sprint 6), corr_id/X‑Request‑ID.
- I (Information Disclosure)
  - Fuite OTP/PII dans logs: filtres de redaction en place; proscrire tout log de code/email complet; Sentry beforeSend supprime cookies/authorization.
  - Enumeration d’état (expired/invalid): messages uniformes “invalid_code”, pas de distinction côté client; Retry‑After pour 429 uniquement.
- D (Denial of Service)
  - Brute‑force OTP: ratelimits IP/session/utilisateur; backoff exponentiel; tarpit court côté serveur.
  - Resend abuse: quotas par session/utilisateur/IP; cooldown progressifs; 429 + Retry‑After.
  - _peek abus en prod: gardé par APP_ENV=test côté backend; CI protège; pas d’exposition en prod.
- E (Elevation of Privilege)
  - Bypass 2FA: liaison stricte challenge↔session_key + contexte (UA/IP); status “one‑time” consommé; invalidation à chaque resend (regénérer code).
  - CSRF bypass: double‑submit enforced; proxys rejettent sans X‑CSRFToken; tests E2E couvrent 403.

6) Politique de secrets et journalisation
- Pepper e‑OTP distinct de SECRET_KEY (EOTP_PEPPER), rotation possible (pepper_id stocké en DB).
- Argon2id (m/t/p) calibré selon infra; re‑hash à la volée non nécessaire (OTP court‑vécu).
- Logs:
  - Pas de secrets/codes/emails; redaction PII maintenue; corrélation par X‑Request‑ID; niveau INFO pour events, DEBUG interdit en prod pour payloads auth.

7) Throttling & anti‑abus sans Turnstile
- Dimensions:
  - verify: p.ex. 6 essais / 10 min par session + 10/min par IP.
  - resend: p.ex. 1 / 30s (palier), 3 / 10 min, 6 / 24h.
- Stockage:
  - Redis clés ratelimit:eotp:(verify|resend):{user|sess|ip}:{window}; TTL = fenêtre.
- Backoff:
  - Exponentiel pour resend; tarpit (sleep 100–300ms) sur verify après N échecs.
- Réponses:
  - 429 avec Retry‑After cohérent; messages génériques (anti‑énum).

8) Politique resend & bounces
- Resend:
  - Invalider le challenge précédent et regénérer un nouveau code (empêche collisions/rejeux).
  - Cooldown initial 30s → 60 → 120s (plafond 10 min).
- Bounces:
  - Sprint 2: webhooks provider ou mailbox de retour; compter bounces par domaine/ip; geler resend si taux anormal.
- Contenu email:
  - Sans PII, sans liens sensibles; inclure watermark anti‑phishing (domain et fingerprint partiel).

9) Vérification de contexte (session/UA/IP)
- UA canonique (lowercase + réduire les tokens dynamiques) → SHA‑224; IP prefix /24 (IPv4) ou /64 (IPv6).
- verify:
  - Par défaut exiger correspondance UA & IP prefix.
  - Flags pour tolérance en mobilité (autoriser mismatch IP si UA constant, logging “low confidence”).
- Stockage:
  - context_ua, context_ip_prefix, corr_id par challenge.

10) Données à caractère personnel (PII) et conformité
- Minimisation: stocker uniquement ce qui est nécessaire (pas d’email en clair dans la table eotp_challenge).
- Conservation:
  - TTL court; purge planifiée (records consommés/expirés supprimés rapidement).
- Droits:
  - Les events agrégés (metrics) ne contiennent pas d’identifiants directs.

11) Plan de tests d’intrusion ciblés (Sprint 7)
- CSRF:
  - Tentatives POST /api/auth/2fa/email/verify sans X‑CSRFToken → 403.
- Brute‑force OTP:
  - Balayage codes 000000→…; vérifier ratelimits et tarpit; jamais de 200 inattendu.
- Resend abuse:
  - Récurrence de resend jusqu’au plafond; vérifier 429 + Retry‑After, cooldown progressif.
- Replay:
  - Réutiliser même code après succès (doit échouer “invalid_code”).
  - Rejouer nonce de requêtes mutatives cibles (déjà testé pour agents/messages).
- Contexte:
  - Changer UA/IP entre issue et verify → mismatch → échec conforme à la politique.
- Leakage:
  - Scanner logs/Sentry pour valeurs OTP, cookies, emails → aucun match.
- Email/DNS:
  - SPF/DKIM/DMARC appliqués; forcer scénarios de spoof → taux de rejet conforme.
- DoS:
  - Inonder verify/resend → vérifier que rate‑limit protège les ressources, sans dégrader autres endpoints.

12) Références internes
- 01 — Cartographie de l’existant: ./01-cartographie-existant.md
- 02 — Architecture cible: ./02-architecture-cible.md
- 05 — Stratégie de tests: ./05-test-strategy.md
- 07 — Observabilité & alerting: ./07-observabilite-alerting.md
- 08 — Mail, transport & DNS: ./08-mail-transport-et-dns.md

13) Points ouverts / TODO
- Calibrage final des fenêtres/quotas (verify/resend) par realm (Dojo vs Clients).
- Décision de tolérance UA/IP (strict vs heuristique) et implémentation par flags.
- Choix du provider email et stratégie de gestion des bounces (hard vs soft).
- Spécifier le format de la chaîne de hachage (journal inviolable) et la politique de rotation.
- Rédiger la matrice STRIDE complète par endpoint lorsque le modèle eotp_challenge sera figé.
