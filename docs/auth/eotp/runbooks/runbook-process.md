# Runbook — Process d’alerte → action → ticket → fermeture
Status: DRAFT
Auteur: Cline (SRE)
Date: 2025-10-17
Version: 0.1

Objectif
- Encadrer la gestion des incidents e‑OTP (observabilité S6) de l’alerte à la clôture, avec rôles/SLAs et traçabilité.

Références
- Observabilité & alerting: ../07-observabilite-alerting.md
- Risques & contingences: ../10-risques-et-contingences.md
- Rapport final: ../rapport-final-eotp.md

RACI (proposé)
- Detection: SRE On‑Call
- Triage/Action: SRE On‑Call + Platform Eng
- Escalade sécurité: Security Officer (si fuite/PII, suspicion attaque)
- Communication produit: PM
- Validation/Clôture: Incident Commander (rotation SRE)

SLA (indication)
- CRIT: TTA ≤ 5 min, Mitigation ≤ 30 min, RCA ≤ 3 j
- WARN: TTA ≤ 15 min, Mitigation ≤ 4 h, RCA si nécessaire

Workflow (étapes)
1) Alerte reçue (Pager/ChatOps): qualifier (CRIT/WARN), récupérer request_id/corr_id, realm impacté.
2) Triage rapide (10 min):
   - Examiner dashboards (“Funnel”, “Sécurité/Abus”, “Délivrabilité”).
   - Vérifier erreurs récentes (proxy_*_failed), 429 spikes, locked rate.
   - Identifier domaine/provider (S2) si délivrabilité.
3) Mitigation initiale:
   - Throttling/flags: assouplir UA/IP si faux positifs, durcir rate‑limits si attaque (S4).
   - Fallbacks: mail → SMTP si provider down (S2), désactiver e‑OTP realm si nécessaire (rollback flags).
   - Purge/backlogs: vérifier Celery beat (S1/S6), exécuter purge si pertinent.
4) Communication:
   - Ticket incident (template): impact, hypothèse, actions, liens (dashboards, logs, events).
   - Annonce interne (canal Ops) si CRIT.
5) Analyse:
   - Rassembler événements auth:eotp_* (corrélation request_id), vérifier hash chain.
   - Examiner ASN/IP outliers, hard bounces, p95 latences.
6) Résolution & validation:
   - Revenir configuration nominale (flags), confirmer retombée alertes, capturer métriques post‑incident.
7) Clôture:
   - Rédiger RCA succinct (cause racine, garde‑fous), lier au ticket, mettre à jour risques/Owners (S6/S7).

Commandes utiles (exemples)
- Celery planifié: celery -A <app> inspect scheduled
- Générer ancre hash chain (voir rapport final, Annexe E)
- Audit sécurité: pip-audit; bandit -q; npm audit

Journal (append-only)
- [YYYY-MM-DD HH:MM] incident_id — résumé — actions — liens
