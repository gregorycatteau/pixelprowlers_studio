#!/usr/bin/env bash
# E-OTP — Vérification quotidienne (S7)
# Orchestration quotidienne des contrôles clés:
#  - Audits sécurité (backend/frontend) → docs/auth/eotp/audits/*
#  - Monitoring ponctuel (obs_sanity, hash-chain, résilience légère)
#  - Résumés et codes de retour archivés par date
#
# Usage:
#   bash tools/schedule_daily.sh
#
# Intégration cron (exemple):
#   0 6 * * * cd /chemin/vers/repo && bash tools/schedule_daily.sh >> tools/reports/cron.log 2>&1
#
# Remarques:
# - Idempotent et non bloquant: collecte les codes de sortie et produit un résumé final.
# - Crée un dossier out par jour: tools/reports/daily/YYYY-MM-DD
# - Requiert que tools/run_audit_ci.sh, tools/monitor_eotp.sh existent.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="${ROOT_DIR}/tools/reports"
DATE_UTC="$(date -u +'%Y-%m-%d')"
DAILY_DIR="${REPORTS_DIR}/daily/${DATE_UTC}"

mkdir -p "${DAILY_DIR}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "${DAILY_DIR}/daily_summary.log"; }
section() { echo -e "\n==== $* ====\n" | tee -a "${DAILY_DIR}/daily_summary.log"; }

header() {
  cat <<'HDR' | tee -a "${DAILY_DIR}/daily_summary.log"
============================================================
E-OTP — Vérification quotidienne (S7)
Audits, monitoring ponctuel, observabilité & hash-chain
============================================================
HDR
}

run_audits() {
  section "Audits sécurité — tools/run_audit_ci.sh"
  if [[ -x "${ROOT_DIR}/tools/run_audit_ci.sh" ]]; then
    set +e
    bash "${ROOT_DIR}/tools/run_audit_ci.sh" 2>&1 | tee "${DAILY_DIR}/run_audit_ci.log"
    RC_AUD=$?
    set -e
    if [[ ${RC_AUD} -eq 0 ]]; then
      log "OK: run_audit_ci.sh exécuté."
    else
      log "WARN: run_audit_ci.sh a retourné ${RC_AUD} (voir ${DAILY_DIR}/run_audit_ci.log)."
    fi
  else
    log "INFO: tools/run_audit_ci.sh introuvable ou non exécutable; étape ignorée."
  fi
}

run_monitor() {
  section "Monitoring ponctuel — tools/monitor_eotp.sh"
  if [[ -x "${ROOT_DIR}/tools/monitor_eotp.sh" ]]; then
    set +e
    bash "${ROOT_DIR}/tools/monitor_eotp.sh" 2>&1 | tee "${DAILY_DIR}/monitor_eotp.log"
    RC_MON=$?
    set -e
    if [[ ${RC_MON} -eq 0 ]]; then
      log "OK: monitor_eotp.sh exécuté."
    else
      log "WARN: monitor_eotp.sh a retourné ${RC_MON} (voir ${DAILY_DIR}/monitor_eotp.log)."
    fi
  else
    log "INFO: tools/monitor_eotp.sh introuvable ou non exécutable; étape ignorée."
  fi
}

run_hash_chain() {
  section "Journal — Vérification hash-chain profonde — verify_log_chain.py --deep"
  if [[ -x "${ROOT_DIR}/tools/verify_log_chain.py" ]]; then
    set +e
    "${ROOT_DIR}/tools/verify_log_chain.py" --deep 2>&1 | tee "${DAILY_DIR}/verify_log_chain.log"
    RC_HASH=$?
    set -e
    if [[ ${RC_HASH} -eq 0 ]]; then
      log "OK: hash-chain valide."
    else
      log "WARN: verify_log_chain.py a retourné ${RC_HASH} (voir ${DAILY_DIR}/verify_log_chain.log)."
    fi
  else
    log "INFO: tools/verify_log_chain.py introuvable; étape ignorée."
  fi
}

run_obs_sanity() {
  section "Observabilité & Alerting — tools/obs_sanity.sh --alerts ops/alerts.json"
  if [[ -f "${ROOT_DIR}/tools/obs_sanity.sh" ]]; then
    set +e
    bash "${ROOT_DIR}/tools/obs_sanity.sh" --alerts "${ROOT_DIR}/ops/alerts.json" 2>&1 | tee "${DAILY_DIR}/obs_sanity.log"
    RC_OBS=$?
    set -e
    if [[ ${RC_OBS} -eq 0 ]]; then
      log "OK: obs_sanity.sh a terminé sans CRIT."
    else
      log "WARN: obs_sanity.sh a retourné ${RC_OBS} (voir ${DAILY_DIR}/obs_sanity.log)."
    fi
  else
    log "INFO: tools/obs_sanity.sh introuvable; étape ignorée."
  fi
}

summary() {
  section "Résumé quotidien"
  printf " - run_audit_ci.sh code: %s\n" "${RC_AUD:-N/A}" | tee -a "${DAILY_DIR}/daily_summary.log"
  printf " - monitor_eotp.sh code: %s\n" "${RC_MON:-N/A}" | tee -a "${DAILY_DIR}/daily_summary.log"
  printf " - verify_log_chain.py code: %s\n" "${RC_HASH:-N/A}" | tee -a "${DAILY_DIR}/daily_summary.log"
  printf " - obs_sanity.sh code: %s\n" "${RC_OBS:-N/A}" | tee -a "${DAILY_DIR}/daily_summary.log"
  log "Dossier quotidien: ${DAILY_DIR}"
  log "Résumé: ${DAILY_DIR}/daily_summary.log"
}

main() {
  header
  log "Repo: ${ROOT_DIR}"
  run_audits
  run_monitor
  run_hash_chain
  run_obs_sanity
  summary
}

main "$@" || {
  log "ERR: Unhandled error — exécution terminée avec avertissements."
  exit 0
}
