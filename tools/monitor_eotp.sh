#!/usr/bin/env bash
# E-OTP — Monitoring ponctuel (S7)
# Exécute un set de vérifications rapides:
#  - Sanity observabilité/alertes (tools/obs_sanity.sh --alerts ops/alerts.json)
#  - Intégrité de la hash-chain (tools/verify_log_chain.py --deep)
#  - Résilience légère (tools/test_resilience.sh) — journalisée
#
# Usage:
#   bash tools/monitor_eotp.sh
#
# Notes:
# - Les sorties sont journalisées dans tools/reports/monitor.log et réutilisent les logs dédiés
#   (ex: tools/reports/resilience.log).
# - Conçu pour être idempotent; n’échoue pas brutalement: les codes d’erreur sont collectés
#   et un résumé final est imprimé.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="${ROOT_DIR}/tools/reports"
MONITOR_LOG="${REPORTS_DIR}/monitor.log"

mkdir -p "${REPORTS_DIR}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "${MONITOR_LOG}"; }
section() { echo -e "\n==== $* ====\n" | tee -a "${MONITOR_LOG}"; }

header() {
  cat <<'HDR' | tee -a "${MONITOR_LOG}"
============================================================
E-OTP — Monitoring ponctuel (S7)
Vérifications rapides: obs/alertes, hash-chain, résilience légère
============================================================
HDR
}

run_obs_sanity() {
  section "Observabilité & Alerting — tools/obs_sanity.sh --alerts ops/alerts.json"
  set +e
  bash "${ROOT_DIR}/tools/obs_sanity.sh" --alerts "${ROOT_DIR}/ops/alerts.json" 2>&1 | tee -a "${MONITOR_LOG}"
  RC_OBS=$?
  set -e
  if [[ ${RC_OBS} -eq 0 ]]; then
    log "OK: obs_sanity.sh a terminé sans CRIT."
  else
    log "WARN: obs_sanity.sh a retourné ${RC_OBS} (voir logs ci-dessus)."
  fi
}

run_hash_chain() {
  section "Journal — Vérification hash-chain profonde — verify_log_chain.py --deep"
  set +e
  "${ROOT_DIR}/tools/verify_log_chain.py" --deep 2>&1 | tee -a "${MONITOR_LOG}"
  RC_HASH=$?
  set -e
  if [[ ${RC_HASH} -eq 0 ]]; then
    log "OK: hash-chain valide."
  else
    log "WARN: verify_log_chain.py a retourné ${RC_HASH} (voir logs)."
  fi
}

run_resilience() {
  section "Résilience légère — tools/test_resilience.sh"
  if [[ -x "${ROOT_DIR}/tools/test_resilience.sh" ]]; then
    # Le script gère déjà son propre journal tools/reports/resilience.log
    set +e
    bash "${ROOT_DIR}/tools/test_resilience.sh" 2>&1 | tee -a "${MONITOR_LOG}"
    RC_RES=$?
    set -e
    if [[ ${RC_RES} -eq 0 ]]; then
      log "OK: test_resilience.sh exécuté (non bloquant)."
    else
      log "WARN: test_resilience.sh a retourné ${RC_RES} (non bloquant, voir logs)."
    fi
  else
    log "INFO: tools/test_resilience.sh introuvable ou non exécutable; étape ignorée."
  fi
}

summary() {
  section "Résumé monitoring"
  printf " - obs_sanity.sh code: %s\n" "${RC_OBS:-N/A}" | tee -a "${MONITOR_LOG}"
  printf " - verify_log_chain.py code: %s\n" "${RC_HASH:-N/A}" | tee -a "${MONITOR_LOG}"
  printf " - test_resilience.sh code: %s\n" "${RC_RES:-N/A}" | tee -a "${MONITOR_LOG}"
  log "Journal: ${MONITOR_LOG}"
  if [[ -f "${REPORTS_DIR}/resilience.log" ]]; then
    log "Journal résilience: ${REPORTS_DIR}/resilience.log"
  fi
  echo | tee -a "${MONITOR_LOG}"
  log "Terminé."
}

main() {
  header
  log "Repo: ${ROOT_DIR}"
  log "Monitor log: ${MONITOR_LOG}"
  run_obs_sanity
  run_hash_chain
  run_resilience
  summary
}

main "$@" || {
  log "ERR: Unhandled error — monitoring terminé avec avertissements."
  exit 0
}
