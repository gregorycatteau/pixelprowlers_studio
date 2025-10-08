#!/usr/bin/env bash
#
# PixelProwlers Studio — Gate Sécurité v1
# Runs:
#   - Trivy (images)  → block if any HIGH/CRITICAL
#   - Semgrep (SAST)  → block on ERROR-level findings (configurable)
#
# Usage:
#   ./ops/security/gate_v1.sh
#   PXP_TRIVY_IMAGES="caddy:2.8.4-alpine python:3.13-slim" ./ops/security/gate_v1.sh
#   PXP_SEMGREP_DIRS="backend frontend" ./ops/security/gate_v1.sh
#
# Exit codes:
#   0  PASS
#   1  FAIL (findings or errors)
#
# Requirements:
#   - Docker available (scanners run in containers)
#   - Internet access (to pull scanner images and semgrep rules)
#
# Notes:
#   - This is a local/minimal CI gate for Sprint 0.
#   - Images are scanned by tag; pin by digest for production.
#   - Trivy blocks on HIGH,CRITICAL (configurable).
#   - Semgrep blocks on ERROR only by default (configurable).
#

set -Eeuo pipefail
IFS=$'\n\t'

# ───────────────────────────────────────────────────────────────────────────────
# Config (override via env)
# ───────────────────────────────────────────────────────────────────────────────

# Default images from docker-compose (Sprint 0)
PXP_TRIVY_IMAGES="${PXP_TRIVY_IMAGES:-caddy:2.8.4-alpine node:22-alpine python:3.13-slim postgres:17.0-alpine nats:2.10.8-alpine n8nio/n8n:1.72.0}"

# Directories to scan with Semgrep (relative to repo root)
PXP_SEMGREP_DIRS="${PXP_SEMGREP_DIRS:-backend frontend}"

# Trivy severity threshold (comma-separated)
PXP_TRIVY_SEVERITY="${PXP_TRIVY_SEVERITY:-HIGH,CRITICAL}"

# Fail Semgrep on WARNINGs too? ("1" to enable; default: only ERROR)
PXP_FAIL_ON_SEMGREP_WARNINGS="${PXP_FAIL_ON_SEMGREP_WARNINGS:-0}"

# Use --ignore-unfixed to reduce noise (Sprint 0 pragmatism)
PXP_TRIVY_IGNORE_UNFIXED="${PXP_TRIVY_IGNORE_UNFIXED:-1}"

# Scanner images (pinned)
TRIVY_IMG="${TRIVY_IMG:-aquasec/trivy:0.53.0}"
SEMGREP_IMG="${SEMGREP_IMG:-semgrep/semgrep:1.102.0}"

# Output formatting
NO_COLOR="${NO_COLOR:-0}"
if [[ "${NO_COLOR}" == "1" ]]; then
  C_RESET=""; C_DIM=""; C_BOLD=""; C_RED=""; C_GRN=""; C_YLW=""; C_CYN=""
else
  C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YLW=$'\033[33m'; C_CYN=$'\033[36m'
fi

# Resolve repo root (this file lives in repo_root/ops/security/gate_v1.sh)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd)"

LOG_DIR="${REPO_ROOT}/ops/security/_logs"
mkdir -p "${LOG_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/gate_${STAMP}.log"

# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────

log()   { printf '%b\n' "${*}" | tee -a "${LOG_FILE}"; }
info()  { log "${C_CYN}[INFO]${C_RESET} ${*}"; }
ok()    { log "${C_GRN}[ OK ]${C_RESET} ${*}"; }
warn()  { log "${C_YLW}[WARN]${C_RESET} ${*}"; }
err()   { log "${C_RED}[FAIL]${C_RESET} ${*}"; }

section() {
  local title=" $* "
  local line
  line="$(printf '%*s' 80 '' | tr ' ' '=')"
  log "${C_BOLD}${line}${C_RESET}" | sed -e 's#.*#'"${C_BOLD}${line}${C_RESET}"'#'
  log "${C_BOLD}${title}${C_RESET}"
  log "${C_BOLD}${line}${C_RESET}"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Command '$1' not found; please install or make it available."
    exit 1
  fi
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    err "Docker is required. Please install and ensure the daemon is running."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker daemon not reachable. Start Docker and retry."
    exit 1
  fi
}

# ───────────────────────────────────────────────────────────────────────────────
# Scanners
# ───────────────────────────────────────────────────────────────────────────────

run_trivy_scan() {
  section "TRIVY — Image Vulnerability Scan"
  info "Scanner image: ${TRIVY_IMG}"
  info "Images to scan: ${PXP_TRIVY_IMAGES}"
  info "Severity gate: ${PXP_TRIVY_SEVERITY}"
  [[ "${PXP_TRIVY_IGNORE_UNFIXED}" == "1" ]] && info "Ignore unfixed: enabled" || info "Ignore unfixed: disabled"

  local trivy_rc_total=0
  local -a IMAGES
  # Split images by spaces respecting word splitting
  # shellcheck disable=SC2206
  IMAGES=(${PXP_TRIVY_IMAGES})

  # Pull scanner image once
  docker pull --quiet "${TRIVY_IMG}" || true

  for img in "${IMAGES[@]}"; do
    log ""
    info "Pulling image ${img} ..."
    docker pull --quiet "${img}" || warn "Could not pull ${img} (continuing to scan cached/local if present)."

    info "Scanning ${img} ..."
    # Build argument list
    local args=(image "--severity" "${PXP_TRIVY_SEVERITY}" "--format" "table" "--scanners" "vuln" "--exit-code" "1")
    [[ "${PXP_TRIVY_IGNORE_UNFIXED}" == "1" ]] && args+=("--ignore-unfixed")

    # Run scan
    # Cache dir persisted between runs for speed
    if docker run --rm \
      -v "${HOME}/.cache/trivy:/root/.cache" \
      "${TRIVY_IMG}" \
      "${args[@]}" "${img}" | tee -a "${LOG_FILE}"
    then
      ok "No blocking vulnerabilities found in ${img}"
    else
      trivy_rc_total=$((trivy_rc_total + 1))
      err "Blocking vulnerabilities detected in ${img} (>= ${PXP_TRIVY_SEVERITY}). See log above."
    fi
  done

  return "${trivy_rc_total}"
}

run_semgrep_scan() {
  section "SEMGREP — Static Application Security Testing (SAST)"
  info "Scanner image: ${SEMGREP_IMG}"
  info "Target directories: ${PXP_SEMGREP_DIRS}"

  # Pull scanner image once
  docker pull --quiet "${SEMGREP_IMG}" || true

  local rc_total=0
  local semgrep_gate="ERROR"
  [[ "${PXP_FAIL_ON_SEMGREP_WARNINGS}" == "1" ]] && semgrep_gate="WARNING"

  local cmd_base=(semgrep scan
    --config p/owasp-top-ten
    --severity "${semgrep_gate}"
    --metrics=off
    --disable-version-check
    --time
  )

  # Exclusions (let Semgrep honor .gitignore too)
  local -a excludes=(--exclude 'node_modules' --exclude '.nuxt' --exclude '.next' --exclude '.venv' --exclude 'venv' --exclude 'dist' --exclude 'build' --exclude '.git')

  for rel in ${PXP_SEMGREP_DIRS}; do
    local target="${REPO_ROOT}/${rel}"
    if [[ ! -d "${target}" ]]; then
      warn "Skip '${rel}' (not found)"
      continue
    fi

    log ""
    info "Scanning ${rel} ..."
    if docker run --rm -t \
      -v "${REPO_ROOT}:/src:ro" \
      -w "/src/${rel}" \
      "${SEMGREP_IMG}" \
      "${cmd_base[@]}" \
      "${excludes[@]}" \
      --output /dev/stdout | tee -a "${LOG_FILE}"
    then
      ok "No blocking findings in ${rel} (gate: ${semgrep_gate})"
    else
      rc_total=$((rc_total + 1))
      err "Blocking findings detected in ${rel} (>= ${semgrep_gate}). See details above."
    fi
  done

  return "${rc_total}"
}

# ───────────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────────

main() {
  section "GATE SÉCURITÉ v1 — Start"
  info "Repo root: ${REPO_ROOT}"
  info "Log file : ${LOG_FILE}"

  require_docker

  local rc_trivy=0
  local rc_semgrep=0

  # Run scanners
  if ! run_trivy_scan; then
    rc_trivy=1
  fi

  if ! run_semgrep_scan; then
    rc_semgrep=1
  fi

  log ""
  section "GATE SUMMARY"
  if [[ "${rc_trivy}" -eq 0 ]]; then ok "Trivy: PASS"; else err "Trivy: FAIL (blocking vulns)"; fi
  if [[ "${rc_semgrep}" -eq 0 ]]; then ok "Semgrep: PASS"; else err "Semgrep: FAIL (blocking findings)"; fi

  local rc=$(( rc_trivy + rc_semgrep ))
  if [[ "${rc}" -eq 0 ]]; then
    ok "Gate Sécurité v1: PASS — 0 blocking issues."
    info "Logs: ${LOG_FILE}"
    exit 0
  else
    err "Gate Sécurité v1: FAIL — see logs for details."
    info "Logs: ${LOG_FILE}"
    log ""
    log "Tips:"
    log "  - Re-run a specific scan:"
    log "      docker run --rm -v \"${HOME}/.cache/trivy:/root/.cache\" \"${TRIVY_IMG}\" image --severity ${PXP_TRIVY_SEVERITY} ${PXP_TRIVY_IGNORE_UNFIXED:+--ignore-unfixed} <image>"
    log "      docker run --rm -v \"${REPO_ROOT}:/src:ro\" -w /src/backend \"${SEMGREP_IMG}\" semgrep scan --config p/owasp-top-ten --severity ${PXP_FAIL_ON_SEMGREP_WARNINGS:+WARNING}${PXP_FAIL_ON_SEMGREP_WARNINGS:-ERROR}"
    log "  - Adjust gate thresholds with env vars (see header)."
    exit 1
  fi
}

main "$@"
