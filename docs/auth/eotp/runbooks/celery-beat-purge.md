# Runbook — Celery Beat (purge TTL eotp_challenge)
Status: DRAFT
Auteur: Cline (SRE)
Date: 2025-10-17
Version: 0.1

Objectif
- Superviser et diagnostiquer la tâche planifiée de purge TTL des challenges e‑OTP (suppression des expirés/consommés + VACUUM ANALYZE).

Références
- Plan migrations & rollback: ../06-plan-migrations-rollback.md
- Observabilité & alerting: ../07-observabilite-alerting.md
- Rapport final: ../rapport-final-eotp.md

Vérifications rapides
- Planification: celery -A <app> inspect scheduled | grep eotp_purge_expired
- Exécution manuelle: python manage.py eotp_purge_expired --dry-run (compte) / sans --dry-run (purge)
- Stats (optionnel): python manage.py eotp_stats (backlog pending par status)
- Logs: grep -i "eotp_purge_expired" (compteurs, durée)
- DB: vérifier index (status, expires_at) et contraintes CHECK

Attendus
- Purge régulière: DELETE WHERE expires_at < now() OR (status IN (consumed, locked) AND created_at < now()-N min)
- VACUUM ANALYZE eotp_challenge post‑purge (intégré à la commande)
- Backlog pending stable (alertes si dérive)

Diagnostic (anomalies)
1) Tâche non planifiée
   - Vérifier celery beat actif (service, logs)
   - Recharger config beat, corriger import de la commande
2) Purge lente / Verrous
   - Regarder verrous de table; vérifier index (status,expires_at)
   - Réduire lot (batch size) dans la commande; exécuter hors pics
3) Backlog en croissance
   - Vérifier TTL/flags; volume de pending; latence DB
   - Alerter Ops; dimensionner maintenance (plusieurs runs)

Observabilité
- Métriques: purge_total, purge_duration_seconds, backlog_pending
- Alertes: backlog_pending > seuil; purge_duration p95 > Xs

Journal (append-only)
- [YYYY-MM-DD HH:MM] action — purge_count — duration — backlog_avant/after — notes
