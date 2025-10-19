#!/usr/bin/env bash
# E-OTP — CI Audits Runner (S7)
# Exécute les audits backend/frontend et archive les rapports dans docs/auth/eotp/audits/.
# Usage:
#   bash tools/run_audit_ci.sh
#
# Variables optionnelles:
#   PIP_AUDIT_FIX=1   # applique --fix sur pip-audit (par défaut: sans --fix)
#   SAFETY_REQ=path   # fichier requirements pour safety (par défaut: autodétection)
#   NPM_AUDIT_ARGS=.. # arguments additionnels passés à `npm audit`
#
# Sorties:
#   docs/auth/eotp/audits/pip-audit.json (ou .md fallback)
#   docs/auth/eotp/audits/bandit.json
#   docs/auth/eotp/audits/safety.txt
#   docs/auth/eotp/audits/npm-audit.json (ou .txt fallback)
#
# Notes:
# - Utilise `poetry run` pour les outils Python (pip-audit, bandit, safety).
# - N'échoue pas brutalement si un outil manque: journalise un avertissement et continue.
# - Conçu pour CI (idempotent). Voir S7-summary.md pour la consolidation.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUDITS_DIR="${ROOT_DIR}/docs/auth/eotp/audits"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

mkdir -p "${AUDITS_DIR}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*"; }

poetry_available() {
  command -v poetry >/dev/null 2>&1
}

npm_available() {
  command -v npm >/dev/null 2>&1
}

detect_safety_requirements() {
  # 1) Variable explicite
  if [[ -n "${SAFETY_REQ:-}" ]]; then
    echo "${SAFETY_REQ}"
    return
  fi
  # 2) Fichiers connus dans backend/
  if [[ -f "${BACKEND_DIR}/requirements-dev.txt" ]]; then
    echo "${BACKEND_DIR}/requirements-dev.txt"
    return
  fi
  if [[ -f "${BACKEND_DIR}/requirements.txt" ]]; then
    echo "${BACKEND_DIR}/requirements.txt"
    return
  fi
  # 3) A défaut, laisser safety inspecter l'env courant (pas d'argument -r)
  echo ""
}

run_pip_audit() {
  if ! poetry_available; then
    log "WARN: poetry introuvable — skip pip-audit"
    return 0
  fi

  local out_json="${AUDITS_DIR}/pip-audit.json"
  local out_md="${AUDITS_DIR}/pip-audit.md"
  local fix_flag=""
  if [[ "${PIP_AUDIT_FIX:-0}" == "1" ]]; then
    fix_flag="--fix"
  fi

  log "INFO: pip-audit ${fix_flag} --desc → ${out_json}"
  set +e
  (cd "${ROOT_DIR}" && poetry run pip-audit ${fix_flag} --desc -f json -o "${out_json}")
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    log "WARN: pip-audit JSON a échoué (code=$status) — fallback vers ${out_md}"
    set +e
    (cd "${ROOT_DIR}" && poetry run pip-audit ${fix_flag} --desc) > "${out_md}" 2>&1
    set -e
  fi
}

run_bandit() {
  if ! poetry_available; then
    log "WARN: poetry introuvable — skip bandit"
    return 0
  fi
  local out_json="${AUDITS_DIR}/bandit.json"
  log "INFO: bandit -r backend -f json -o ${out_json}"
  set +e
  (cd "${ROOT_DIR}" && poetry run bandit -r backend -f json -o "${out_json}")
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    log "WARN: bandit a retourné $status — voir ${out_json} si partiel, sinon logs CI."
  fi
}

run_safety() {
  if ! poetry_available; then
    log "WARN: poetry introuvable — skip safety"
    return 0
  fi
  local req_file
  req_file="$(detect_safety_requirements)"
  local out_txt="${AUDITS_DIR}/safety.txt"

  if [[ -n "${req_file}" && -f "${req_file}" ]]; then
    log "INFO: safety check -r ${req_file} → ${out_txt}"
    set +e
    (cd "${ROOT_DIR}" && poetry run safety check -r "${req_file}") > "${out_txt}" 2>&1
    set -e
  else
    log "INFO: safety check (sans -r, inspection de l'env) → ${out_txt}"
    set +e
    (cd "${ROOT_DIR}" && poetry run safety check) > "${out_txt}" 2>&1
    set -e
  fi
}

run_npm_audit() {
  if ! npm_available; then
    log "WARN: npm introuvable — skip npm audit"
    return 0
  fi

  local out_json="${AUDITS_DIR}/npm-audit.json"
  local out_txt="${AUDITS_DIR}/npm-audit.txt"
  local extra="${NPM_AUDIT_ARGS:-}"

  log "INFO: npm audit ${extra} --json → ${out_json}"
  set +e
  (cd "${FRONTEND_DIR}" && npm audit ${extra} --json) > "${out_json}" 2>&1
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    log "WARN: npm audit JSON a échoué (code=$status) — fallback vers ${out_txt}"
    set +e
    (cd "${FRONTEND_DIR}" && npm audit ${extra}) > "${out_txt}" 2>&1
    set -e
  fi
}

summary() {
  log "==== Résumé des sorties ===="
  for f in "pip-audit.json" "pip-audit.md" "bandit.json" "safety.txt" "npm-audit.json" "npm-audit.txt"; do
    if [[ -f "${AUDITS_DIR}/${f}" ]]; then
      log "OK: ${AUDITS_DIR}/${f}"
    fi
  done
  log "==== Fin des audits ===="
}

main() {
  log "Repo: ${ROOT_DIR}"
  log "Audits dir: ${AUDITS_DIR}"
  run_pip_audit
  run_bandit
  run_safety
  run_npm_audit
  summary
}

main "$@"
