# E‑OTP — Feedback Loop (S9) — Supervision adaptative post Go‑Live

Objectif
- Finaliser la boucle d’observabilité intelligente pour l’e‑OTP.
- Exploiter les données opérationnelles agrégées (logs, métriques, alertes) pour un recalibrage adaptatif contrôlé (±10%).
- Garantir un cycle sécurisé, PII‑safe, sans export externe.

Vue d’ensemble (flux)
1) Collecte (journalière ou à la demande)
   - tools/monitor_eotp.sh agrège des vérifications ponctuelles (obs_sanity, hash‑chain, résilience).
   - tools/schedule_daily.sh orchestre audits + monitoring + scellage/obs.
   - manage.py telemetry_collect consolide sur fenêtre (ex: 24h) → ops/telemetry/aggregated/YYYY‑MM‑DD.jsonl
2) Tendances
   - studio_core.telemetry.trends résume et calcule risk_operational_score ∈ [0,1]
   - Sortie: tools/reports/trends/YYYY‑MM‑DD.json (moyenne mobile, σ, drift)
3) Runtime
   - studio_core.telemetry.runtime lit le dernier résumé (trends/*.json)
   - get_latest_risk_score(); adaptive_threshold(base, score) → seuils effectifs
4) Adaptation Gatekeeper
   - eotp.gatekeeper.get_adaptive_gate_threshold() applique ±10% sur GATE_RISK_THRESHOLD
   - record_auth_event(endpoint="gatekeeper", decision="self_tune", …) trace l’auto‑ajustement (PII‑safe)
5) Debug (DEV/TEST uniquement)
   - /debug/eotp-stats expose:
     {
       "risk_operational_score": 0.42,
       "adaptive_gate_threshold": 0.68,
       "stats": { … }
     }

Schéma (conceptuel)
aggregator (JSONL) → trends (JSON) → runtime (score) → gatekeeper (threshold adaptatif) → record_auth_event → telemetry_collect (nouveau cycle)

Composants clés
- Collecte:
  - backend/studio_core/telemetry/aggregator.py
  - manage.py telemetry_collect — ops/telemetry/aggregated/*.jsonl + tools/reports/trends/*.json
- Tendances:
  - backend/studio_core/telemetry/trends.py (moving_avg, moving_std, drift, risk_operational_score)
- Runtime:
  - backend/studio_core/telemetry/runtime.py (lecture dernier trends + adaptation de seuils)
- Adaptation:
  - backend/eotp/gatekeeper.py:get_adaptive_gate_threshold() (±10%) + log self_tune
- Journal & preuves:
  - backend/studio_core/obs/journal.py: seal_day() (hash‑chain + HMAC)
  - manage.py seal_day → ops/reports/seals/YYYY‑MM‑DD.txt

Pseudo‑code (flow de collecte et adaptation)
- Cron quotidien:
  - bash tools/schedule_daily.sh
    - bash tools/run_audit_ci.sh → docs/auth/eotp/audits/
    - bash tools/monitor_eotp.sh → tools/reports/monitor.log (+resilience.log)
    - poetry run python manage.py telemetry_collect --window 24h
      - aggregate_window(repo_root, 24h) → JSONL (aggregated)
      - summarize_trends_from_records → trends JSON (moving_avg/std + score)
    - poetry run python manage.py seal_day --date $(date +%F)
- À l’exécution (runtime):
  - score = runtime.get_latest_risk_score()
  - thr_eff = runtime.adaptive_threshold(GATE_RISK_THRESHOLD, score)
  - gatekeeper.get_adaptive_gate_threshold() journalise un “self_tune” (record_auth_event)
  - /debug/eotp-stats (DEV/TEST) expose score/threshold

Commandes utiles
- Collecte & scellage:
  - poetry run python manage.py telemetry_collect --window 24h
  - poetry run python manage.py seal_day --date $(date +%F)
- Comparaison de tendances:
  - bash tools/test_trends.sh --threshold 5
- Debug (DEV uniquement):
  - curl -s http://127.0.0.1:8000/debug/eotp-stats | jq .
- Audit final:
  - bash tools/run_audit_ci.sh
- Intégrité journal:
  - ./tools/verify_log_chain.py --deep

Sécurité & conformité
- PII‑safe: agrégations statistiques, aucun user_id/email exporté.
- Aucune sortie externe (fichiers locaux sous ops/ et tools/reports/).
- Clé HMAC (OPS_SIGNING_KEY) uniquement locale.
- /debug… désactivé en production (garde dans views).
- Adaptation bornée à ±10% (runtime.adaptive_threshold).

Maintenance
- Revoir régulièrement les seuils d’alerte (ops/alerts.json) en corrélation avec trends.
- Archiver les sceaux journaliers (ops/reports/seals) et exécuter verify_log_chain.py --deep.
- Tenir CHANGELOG‑S8/S9 à jour avec captures/sorties (telemetry_collect, seal_day, test_trends).

Annexes & références
- backend/studio_core/telemetry/{aggregator.py,trends.py,runtime.py}
- backend/eotp/gatekeeper.py
- backend/studio_core/obs/journal.py (seal_day)
- tools/test_trends.sh
- docs/auth/eotp/07-observabilite-alerting.md
- docs/auth/eotp/08-monitoring-intelligent.md
- docs/auth/eotp/CHANGELOG-S8.md, docs/auth/eotp/CHANGELOG-S9.md (à compléter)
