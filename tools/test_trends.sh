#!/usr/bin/env bash
# E-OTP — Trends diff (S9)
# Compare deux fichiers trends JSON (tools/reports/trends/YYYY-MM-DD.json)
# et affiche la variation en % des indicateurs principaux. Détecte un drift si
# une variation dépasse le seuil (--threshold, %).
#
# Usage:
#   bash tools/test_trends.sh --date1 2025-10-18 --date2 2025-10-19 --threshold 5
#   bash tools/test_trends.sh --a path/to/old.json --b path/to/new.json --threshold 10
#
# Sortie:
#   - Tableau "metric, old, new, delta%" sur stdout
#   - "drift detected" si delta% > threshold pour un indicateur suivi
#   - Log sauvegardé dans tools/reports/trends/diff-<date1>-<date2>.log
#
# Dépendances:
#   - jq (par défaut présent dans l'environnement de validation)

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRENDS_DIR="${ROOT_DIR}/tools/reports/trends"
REPORTS_DIR="${ROOT_DIR}/tools/reports/trends"

DATE1=""
DATE2=""
FILE_A=""
FILE_B=""
THRESHOLD="5" # en pourcentage

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date1) DATE1="${2:-}"; shift 2 ;;
    --date2) DATE2="${2:-}"; shift 2 ;;
    --a) FILE_A="${2:-}"; shift 2 ;;
    --b) FILE_B="${2:-}"; shift 2 ;;
    --threshold) THRESHOLD="${2:-5}"; shift 2 ;;
    -h|--help)
      grep -E '^#( |!|$)' "${BASH_SOURCE[0]}" | sed -E 's/^# ?//'
      exit 0
      ;;
    *)
      echo "WARN: argument ignoré: $1" >&2
      shift
      ;;
  esac
done

# Résolution des fichiers si dates fournies
if [[ -n "${DATE1}" && -z "${FILE_A}" ]]; then
  FILE_A="${TRENDS_DIR}/${DATE1}.json"
fi
if [[ -n "${DATE2}" && -z "${FILE_B}" ]]; then
  FILE_B="${TRENDS_DIR}/${DATE2}.json"
fi

# Par défaut: aujourd'hui et hier (UTC)
if [[ -z "${FILE_A}" || -z "${FILE_B}" ]]; then
  D2="$(date -u +%F)"
  D1="$(date -u -d 'yesterday' +%F 2>/dev/null || python - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(tz=timezone.utc)-timedelta(days=1)).strftime('%Y-%m-%d'))
PY
)"
  FILE_A="${FILE_A:-${TRENDS_DIR}/${D1}.json}"
  FILE_B="${FILE_B:-${TRENDS_DIR}/${D2}.json}"
  DATE1="${DATE1:-${D1}}"
  DATE2="${DATE2:-${D2}}"
else
  # Extraire dates pour nom du log si possible
  DATE1="${DATE1:-$(basename "${FILE_A}" .json || echo old)}"
  DATE2="${DATE2:-$(basename "${FILE_B}" .json || echo new)}"
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERR: jq est requis" >&2
  exit 2
fi

if [[ ! -f "${FILE_A}" ]]; then
  echo "ERR: fichier introuvable: ${FILE_A}" >&2
  exit 2
fi
if [[ ! -f "${FILE_B}" ]]; then
  echo "ERR: fichier introuvable: ${FILE_B}" >&2
  exit 2
fi

mkdir -p "${REPORTS_DIR}"
LOG_FILE="${REPORTS_DIR}/diff-${DATE1//-/}${DATE2//-/}.log"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "${LOG_FILE}"; }

# Récupérer les valeurs num
get_num() {
  local file="$1" key="$2"
  jq -r --arg k "${key}" '.[$k] // 0' "${file}" 2>/dev/null | awk '{if ($0=="true") print 1; else if ($0=="false") print 0; else print $0}'
}

# Variables d'intérêt
METRICS=(
  "risk_operational_score"
  "moving_avg"
  "moving_std"
  "last_weighted_rate"
)

# Totaux (imbriqué dans .totals)
get_total() {
  local file="$1" key="$2"
  jq -r --arg k "${key}" '.totals[$k] // 0' "${file}" 2>/dev/null
}

TOTAL_KEYS=("crit" "warn" "info" "events")

# Impression d'un en-tête CSV simple
print_header() {
  printf "metric,old,new,delta%%\n" | tee -a "${LOG_FILE}"
}

# Calcul delta %
delta_percent() {
  local old="$1" new="$2"
  # éviter division par zéro
  if awk 'BEGIN{exit !(('"${old}"'==0))}'; then
    if awk 'BEGIN{exit !(('"${new}"'==0))}'; then
      echo "0"
    else
      echo "100"
    fi
  else
    awk -v o="${old}" -v n="${new}" 'BEGIN{
      d = (n - o) / ( (o==0)?1:o ) * 100.0;
      printf("%.2f", d);
    }'
  fi
}

DRIFT=0
print_header

# Mesures principales
for k in "${METRICS[@]}"; do
  A_VAL="$(get_num "${FILE_A}" "${k}")"
  B_VAL="$(get_num "${FILE_B}" "${k}")"
  DP="$(delta_percent "${A_VAL}" "${B_VAL}")"
  printf "%s,%s,%s,%s\n" "${k}" "${A_VAL}" "${B_VAL}" "${DP}" | tee -a "${LOG_FILE}"
  # Détection drift si delta% > threshold
  awk -v dp="${DP}" -v th="${THRESHOLD}" 'BEGIN{exit !(dp>th)}' && DRIFT=1 || true
done

# Totaux
for k in "${TOTAL_KEYS[@]}"; do
  A_VAL="$(get_total "${FILE_A}" "${k}")"
  B_VAL="$(get_total "${FILE_B}" "${k}")"
  DP="$(delta_percent "${A_VAL}" "${B_VAL}")"
  printf "totals.%s,%s,%s,%s\n" "${k}" "${A_VAL}" "${B_VAL}" "${DP}" | tee -a "${LOG_FILE}"
  awk -v dp="${DP}" -v th="${THRESHOLD}" 'BEGIN{exit !(dp>th)}' && DRIFT=1 || true
done

if [[ "${DRIFT}" -eq 1 ]]; then
  log "drift detected (threshold=${THRESHOLD}%)"
  exit 1
else
  log "no significant drift (threshold=${THRESHOLD}%)"
  exit 0
fi
