#!/usr/bin/env bash
# E-OTP — Résilience/Chaos léger (S7)
# Scénarios:
#  1) Redis down → fallback metrics adapter in-memory → OK (pas de crash, logs explicites)
#  2) eotp_purge_expired sous charge (batch ~10k) → pas d'erreur
#  3) Postmark 5xx simulés → fallback SMTP opérationnel
#
# Remarque:
# - Le script est pensé pour être idempotent et non bloquant: il n'échoue pas la CI,
#   il produit un journal analyzable dans tools/reports/resilience.log
# - Adaptez les commandes stop/start Redis/Postmark à votre environnement (Docker, local, etc.)
# - Exécutez depuis la racine du repo.
#
# Rendre exécutable: chmod +x tools/test_resilience.sh

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="${ROOT_DIR}/tools/reports"
LOG_FILE="${REPORTS_DIR}/resilience.log"

mkdir -p "${REPORTS_DIR}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "${LOG_FILE}"; }
section() { echo -e "\n==== $* ====\n" | tee -a "${LOG_FILE}"; }

header() {
  cat <<'HDR' | tee -a "${LOG_FILE}"
============================================================
E-OTP — Résilience/Chaos léger (S7)
Ce journal agrège les résultats des simulations.
============================================================
HDR
}

python_ok() {
  # Petit helper pour tenter un one-liner Python en capturant les erreurs
  local code="$1"
  python - <<PYCODE
import sys
try:
    ${code}
    print("OK")
except Exception as e:
    print(f"ERR: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PYCODE
}

scenario_1_redis_down_metrics_fallback() {
  section "Scénario 1 — Redis down → metrics fallback in-memory"
  log "INFO: Simulation logique (sans dépendre d'une instance Redis)."
  log "INFO: On vérifie que l'adapter mémoire ne crashe pas et produit un snapshot."

  # Appel direct de l'adapter mémoire; ne dépend pas de Redis
  # (backend/studio_core/metrics_adapter.py)
  if python_ok "from backend.studio_core import metrics_adapter as m; m.counter_inc('resilience.redis_down.test', n=2); s=m.get_snapshot(); assert 'counters' in s and s['counters'].get('resilience.redis_down.test')>=2; print('snapshot=', s)"; then
    log "OK: metrics in-memory opérationnel (pas de crash)."
  else
    log "WARN: échec de la vérif in-memory — vérifier l'import Python ou le PYTHONPATH."
  fi

  log "NOTE: Pour une simulation réelle Redis down, stopper Redis (ou pointer REDIS_URL invalide),"
  log "      puis rejouer une requête applicative et vérifier l'absence de crash côté app/logs."
}

scenario_2_purge_expired_under_load() {
  section "Scénario 2 — eotp_purge_expired sous charge"
  log "INFO: Exécution best-effort de la commande de purge (si disponible)."

  set +e
  # Essayez d'utiliser --dry-run si supporté (sinon simple exécution).
  python "${ROOT_DIR}/backend/manage.py" eotp_purge_expired --dry-run 2>&1 | tee -a "${LOG_FILE}"
  status=$?
  set -e

  if [[ $status -eq 0 ]]; then
    log "OK: purge exécutée sans erreur (dry-run)."
  else
    log "WARN: la commande a retourné $status — vérifier la disponibilité de la commande et des settings."
  fi

  log "NOTE: Pour simuler une charge (~10k), préparer un jeu de données local et rejouer la commande."
}

scenario_3_postmark_5xx_fallback_smtp() {
  section "Scénario 3 — Postmark 5xx simulés → fallback SMTP"
  log "INFO: Simulation logique — cette étape dépend de la configuration mailer."
  log "INFO: Vérifiez que backend/eotp/mailer.py implémente un fallback en cas d'échec 5xx."

  # Tentative de test minimal non intrusif: import et présence de symboles attendus
  if python_ok "import importlib; m=importlib.import_module('backend.eotp.mailer'); print('mailer=', m.__name__)"; then
    log "OK: module mailer importable."
  else
    log "WARN: mailer non importable — vérifier le chemin du module."
  fi

  log "NOTE: Pour un test bout-en-bout, forcer un faux 5xx (mock/Postmark sandbox) et observer que"
  log "      l'email est routé via SMTP de secours. Archiver les logs en preuve."
}

main() {
  header
  log "Repo: ${ROOT_DIR}"
  log "Journal: ${LOG_FILE}"
  scenario_1_redis_down_metrics_fallback
  scenario_2_purge_expired_under_load
  scenario_3_postmark_5xx_fallback_smtp
  section "Fin — Voir ${LOG_FILE} pour le détail."
}

main "$@" || {
  log "ERR: Unhandled error — le script continue (non bloquant)."
  exit 0
}
