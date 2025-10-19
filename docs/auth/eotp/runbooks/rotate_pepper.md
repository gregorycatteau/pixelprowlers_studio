# Runbook — Rotation du pepper e‑OTP (EOTP_PEPPER)
Status: DRAFT
Auteur: Cline (SRE)
Date: 2025-10-17
Version: 0.1

Objectif
- Définir une procédure sûre pour faire pivoter le pepper Argon2id utilisé pour les OTP (EOTP_PEPPER), sans fuite de secrets et avec vérifications post‑rotation.

Références
- Rapport final: ../rapport-final-eotp.md (paramètres §3.1, annexes)
- Observabilité & alerting: ../07-observabilite-alerting.md
- Risques & contingences: ../10-risques-et-contingences.md

Pré‑checks (planification)
- Générer un nouveau secret (stockage secret manager, jamais en repo).
- Définir pepper_id associé (string courte, ex: eotppepper-2025Q4).
- Noter les environnements (dev/stage/prod) et fenêtres maintenance.
- Confirmer que seuls hash de codes éphémères (OTP) sont stockés (pas de re‑hash nécessaire).

Étapes (rotation progressive)
1) Dev/Stage
   - Injecter NEW_EOTP_PEPPER (+ pepper_id) via env/secrets.
   - Déployer backend (lecture NEW_EOTP_PEPPER); conserver OLD_EOTP_PEPPER par sécurité (grace) si code le supporte, sinon basculer en “forward‑only”.
   - Valider S1→S3 (issue/verify/resend) + E2E Playwright (happy/invalid/expired).
   - Vérifier events/métriques eotp_*; grep: aucune fuite secret.
2) Prod (progressive)
   - Bascule par realm (Dojo → Clients).
   - Surveiller alertes (success rate, 429, locked); rollback = ré‑injecter OLD_EOTP_PEPPER et redéployer si incident.

Post‑checks
- Observabilité: success_rate stable, locked_rate nominal, p95 issue→ok sous seuil.
- Logs: aucun secret; Sentry beforeSend OK.
- Documenter pepper_id actif (inventaire ops), calendrier prochaine rotation.

Rollback
- Ré‑appliquer OLD_EOTP_PEPPER + redéploiement.
- Ouvrir ticket incident + RCA si besoin.

Notes
- Les OTP sont éphémères: aucun re‑hash/“migration” nécessaire.
- S’assurer que la rotation ne modifie pas la canonicalisation des events (S6).
