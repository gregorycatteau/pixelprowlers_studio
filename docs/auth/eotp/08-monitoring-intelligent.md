# E‑OTP — Monitoring Intelligent (S8–S9)

Objectif
- Décrire l’architecture de supervision intelligente e‑OTP.
- Détail des composants: agrégation (aggregator), tendances (trends), exposition runtime, recalibrage adaptatif Gatekeeper.
- Garanties: PII‑safe, aucune exportation externe, scellement hash‑chain + HMAC.

1) Architecture générale
Flux logique:
- Collecte:
  - tools/monitor_eotp.sh (sanity, hash‑chain, résilience légère)
  - tools/schedule_daily.sh (audits, monitoring, collecte, scellement)
  - manage.py telemetry_collect — fenêtre glissante (ex: 24h), écrit:
    - ops/telemetry/aggregated/YYYY‑MM‑DD.jsonl (événements normalisés)
    - tools/reports/trends/YYYY‑MM‑DD.json (résumé: moyenne mobile, σ, drift, risk_operational_score)
- Runtime:
  - studio_core.telemetry.runtime lit le dernier trends JSON
  - get_latest_risk_score() → risk_operational_score (0..1)
  - adaptive_threshold(base, score) → seuils effectifs bornés ±10%
- Adaptation:
  - eotp.gatekeeper.get_adaptive_gate_threshold() applique ±10%
  - record_auth_event(… decision="self_tune") journalise l’auto‑ajustement (PII‑safe)
- Traçabilité:
  - studio_core.obs.journal.seal_day() scelle quotidiennement le journal (hash‑chain + HMAC)
  - Preuves: ops/reports/seals/YYYY‑MM‑DD.txt
  - Intégrité: tools/verify_log_chain.py --deep

2) Composants clés
- backend/studio_core/telemetry/aggregator.py
  - aggregate_window(repo_root, window, stats_snapshot) → [TelemetryRecord]
  - write_aggregated_jsonl(records, output_dir) → JSONL par jour
- backend/studio_core/telemetry/trends.py
  - summarize_trends_from_records(records, window) → TrendSummary
  - write_daily_trends(summary, repo_root) → trends/YYYY‑MM‑DD.json
- backend/studio_core/telemetry/runtime.py
  - get_latest_trends_summary(), get_latest_risk_score()
  - adaptive_threshold(base, risk_operational_score) → borne [0,1], ±10%
- backend/eotp/gatekeeper.py
  - get_adaptive_gate_threshold() — lit dernier score (runtime) et applique adaptation
- backend/studio_core/obs/journal.py
  - seal_day(signing_key, date, file) — HMAC‑SHA256 + vérification de chaîne
- backend/studio_core/views.py
  - /debug/eotp-stats (DEV/TEST) expose les valeurs runtime (voir ci‑dessous)

3) Runtime & Debug View (DEV/TEST)
Endpoint: GET /debug/eotp-stats
- Garde: désactivé en prod (vérification APP_ENV).
- Réponse exemple:
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
- risk_operational_score: issu de tools/reports/trends/YYYY‑MM‑DD.json (champ risk_operational_score)
- adaptive_gate_threshold: résultat de gatekeeper.get_adaptive_gate_threshold() (±10% sur GATE_RISK_THRESHOLD)

4) Outils d’analyse et d’audit
- tools/test_trends.sh
  - Compare trends JSON de deux jours (ex: --date1 2025‑10‑18 --date2 2025‑10‑19)
  - Affiche delta% des métriques et “drift detected” si > threshold
  - Journal: tools/reports/trends/diff‑<date1><date2>.log
- tools/run_audit_ci.sh
  - Exécute pip‑audit, Bandit, Safety, npm audit
  - Rapports sous docs/auth/eotp/audits/

5) Sécurité & conformité
- PII‑safe: aucun identifiant utilisateur dans les agrégations/rapports.
- Aucune sortie externe: fichiers locaux (ops/ et tools/reports/).
- Clé HMAC locale: OPS_SIGNING_KEY (non commité).
- /debug… interdit en prod.
- Adaptation bornée ±10% via runtime.adaptive_threshold().

6) Commandes utiles
- Collecte & tendances:
  - poetry run python manage.py telemetry_collect --window 24h
- Comparaison de tendances:
  - bash tools/test_trends.sh --threshold 5
- Scellement & intégrité:
  - poetry run python manage.py seal_day --date $(date +%F)
  - ./tools/verify_log_chain.py --deep
- Monitoring ponctuel & quotidien:
  - bash tools/monitor_eotp.sh
  - bash tools/schedule_daily.sh
- Debug (DEV/TEST):
  - curl -s http://127.0.0.1:8000/debug/eotp-stats | jq .

7) Tests pertinents (S9)
- backend/studio_core/tests/test_telemetry_intelligence.py
  - Aggregation output format (JSONL)
  - Trends (risk_operational_score borné [0,1])
  - Gatekeeper adaptive threshold (±10%)
  - Scellement journal (HMAC, hash‑chain)

8) Maintenance
- Suivre les drift signalés (tools/test_trends.sh) et corréler avec ops/alerts.json.
- Ajuster graduellement les seuils d’alerting avec retour d’expérience (S4→S9).
- Conserver les preuves de scellement quotidiennes (ops/reports/seals) et valider régulièrement l’intégrité (verify_log_chain.py --deep).

Références
- docs/auth/eotp/09-feedback-loop.md (boucle complète)
- docs/auth/eotp/CHANGELOG-S9.md (résumé des changements)
- docs/auth/eotp/07-observabilite-alerting.md (cycle S4→S9)
