# E‑OTP — CHANGELOG S9 (Finalisation Adaptive Monitoring & Feedback Loop)

Résumé exécutif
- Exposition runtime des indicateurs d’intelligence opérationnelle:
  - risk_operational_score (0..1)
  - adaptive_gate_threshold (seuil Gate recalibré ±10% en DEV/TEST)
- Outils d’analyse de tendance:
  - trends.json journalier + script tools/test_trends.sh (détection de drift)
- Boucle de feedback bouclée:
  - aggregator (JSONL) → trends (JSON) → runtime (score) → gatekeeper (±10%) → record_auth_event → telemetry_collect
- Traçabilité:
  - Scellement quotidien (hash‑chain + HMAC) via manage.py seal_day, preuves sous ops/reports/seals/
- Tests S9:
  - Aggregation/trends/gatekeeper/seal_day couverts et bornés (see backend/studio_core/tests/test_telemetry_intelligence.py)

Changements clés (S8 → S9)
1) Exposition runtime (DEV/TEST)
- backend/studio_core/views.py (debug_eotp_stats) expose:
  - "risk_operational_score": <float|null>
  - "adaptive_gate_threshold": <float|null>
  - "stats": snapshot de l’adapter de métriques
- sources:
  - studio_core.telemetry.runtime.get_latest_risk_score()
  - eotp.gatekeeper.get_adaptive_gate_threshold()

2) Gatekeeper — adaptation contrôlée
- backend/eotp/gatekeeper.py:
  - get_adaptive_gate_threshold(): applique runtime.adaptive_threshold (±10% selon score)
  - Enregistre un “self_tune” PII‑safe via record_auth_event

3) Télémétrie et tendances
- studio_core/telemetry/aggregator.py: JSONL quotidien (ops/telemetry/aggregated/YYYY‑MM‑DD.jsonl)
- studio_core/telemetry/trends.py: moving_avg, moving_std, drift, risk_operational_score
- manage.py telemetry_collect: produit aggregated + trends (tools/reports/trends/YYYY‑MM‑DD.json)

4) Scellement (hash‑chain + HMAC)
- studio_core/obs/journal.py: seal_day(signing_key, date, file)
- manage.py seal_day: écrit ops/reports/seals/YYYY‑MM‑DD.txt
- verify_log_chain.py --deep: contrôle d’intégrité

5) Outils & scripts
- tools/test_trends.sh: compare deux fichiers trends JSON, affiche variations (%) et signale “drift detected” si delta > threshold
- tools/run_audit_ci.sh, tools/monitor_eotp.sh, tools/schedule_daily.sh: conservés et intégrés à la boucle

Exemple /debug/eotp-stats (DEV/TEST)
{
  "ok": true,
  "stats": {
    "ts": 1739876543,
    "counters": { "pp_login_ok": 123, "pp_login_fail": 7 },
    "histograms": {}
  },
  "risk_operational_score": 0.42,
  "adaptive_gate_threshold": 0.68
}

Commandes utiles
- Collecte & tendances:
  - poetry run python manage.py telemetry_collect --window 24h
- Comparaison de tendances:
  - bash tools/test_trends.sh --threshold 5
- Scellement & intégrité:
  - poetry run python manage.py seal_day --date $(date +%F)
  - ./tools/verify_log_chain.py --deep
- Debug (DEV/TEST):
  - curl -s http://127.0.0.1:8000/debug/eotp-stats | jq .

Tests S9 livrés
- backend/studio_core/tests/test_telemetry_intelligence.py
  - test_telemetry_aggregation_output_format()
  - test_trend_detection_thresholds()
  - test_gatekeeper_adaptive_threshold_changes()
  - test_seal_day_integrity()

Sécurité & conformité
- PII‑safe: aucune donnée nominative exportée
- Aucune sortie externe (fichiers locaux repos/ops/tools)
- Clé HMAC locale: OPS_SIGNING_KEY
- /debug désactivé en production
- Adaptation limitée et bornée à ±10%

Prochaines étapes (ops)
- Relancer outils d’audit: bash tools/run_audit_ci.sh
- Consolider docs/auth/eotp/audits/S9-summary.md (tableau avant→après)
- Exécuter la batterie de tests e‑OTP (S1→S9)
- Sceller le journal du jour et archiver la preuve

DoD S9
- [ ] risk_operational_score + adaptive_gate_threshold exposés (DEV/TEST)
- [ ] tests “telemetry, trends, adaptive, seal_day” verts
- [ ] audits S9 consolidés
- [ ] scellement HMAC/chaîne vérifiés
- [ ] branche feat/front/dashboard-projects prête pour merge/stabilisation
