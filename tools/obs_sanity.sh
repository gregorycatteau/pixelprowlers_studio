#!/usr/bin/env bash
# Simple observability sanity tool
# - Validates ops/alerts.json against ops/alerts.schema.json
# - Uses ajv (if available) or falls back to jq structural checks
# - Evaluates a subset of rules against /debug/eotp-stats (approx, sans Prometheus)
#
# Usage:
#   tools/obs_sanity.sh validate [--alerts PATH] [--schema PATH]
#   tools/obs_sanity.sh check [--source URL|FILE] [--alerts PATH]
#   tools/obs_sanity.sh [--source URL|FILE] [--alerts PATH]   # alias de 'check'
#
# Examples:
#   tools/obs_sanity.sh validate
#   tools/obs_sanity.sh validate --alerts ops/alerts.json --schema ops/alerts.schema.json
#   tools/obs_sanity.sh --source http://127.0.0.1:8000/debug/eotp-stats --alerts ops/alerts.json
#   tools/obs_sanity.sh check --source backend/var/eotp_stats.json --alerts ops/alerts.json
#
# Notes:
# - L'évaluation des expressions est approximative: rate(x) est interprété comme la valeur
#   courante du compteur x (pas de fenêtre réelle). Suffisant pour une sanity locale.
# - Les fonctions supportées dans les expressions: +, -, *, /, parenthèses, min(), max().
# - Toute donnée sensible/PII ne doit jamais apparaître dans les stats exposées.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
SUBCOMMAND="validate"
ALERTS="${REPO_ROOT}/ops/alerts.json"
SCHEMA="${REPO_ROOT}/ops/alerts.schema.json"
SOURCE=""
PRINT_JSON="0"

usage() {
  cat >&2 <<'EOF'
Usage:
  tools/obs_sanity.sh validate [--alerts PATH] [--schema PATH]
  tools/obs_sanity.sh check [--source URL|FILE] [--alerts PATH]
  tools/obs_sanity.sh [--source URL|FILE] [--alerts PATH]    # alias de 'check'

Options:
  --alerts PATH   Chemin vers le JSON d'alertes (default: ops/alerts.json)
  --schema PATH   Chemin vers le JSON-Schema (default: ops/alerts.schema.json) [validate]
  --source ARG    URL (http/https) de /debug/eotp-stats ou chemin de fichier JSON [check]
  --print-json    Pour 'check': imprime les stats brutes (debug)

Notes:
- Si 'ajv' est installé, 'validate' utilise JSON Schema 2020-12.
- Sinon, fallback 'jq' (contrôles structurels, pas de additionalProperties:false).
- 'check' évalue les expressions avec un interpréteur Python sécurisé (AST), sans Python externe.
EOF
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# Decide subcommand:
# - Si premier argument commence par '-' ou est vide, on choisit 'check' (alias)
if [[ $# -gt 0 ]]; then
  if [[ "$1" == "validate" || "$1" == "check" ]]; then
    SUBCOMMAND="$1"; shift || true
  elif [[ "$1" == -* ]]; then
    SUBCOMMAND="check"
  fi
else
  SUBCOMMAND="check"
fi

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --alerts)
      ALERTS="$2"; shift 2 ;;
    --schema)
      SCHEMA="$2"; shift 2 ;;
    --source)
      SOURCE="$2"; shift 2 ;;
    --print-json)
      PRINT_JSON="1"; shift 1 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

# Resolve to absolute paths if given relatively (when applicable)
if [[ -n "${ALERTS:-}" && "${ALERTS}" != http* ]]; then
  ALERTS="$(realpath -m "${ALERTS}")"
fi
if [[ -n "${SCHEMA:-}" && "${SCHEMA}" != http* ]]; then
  SCHEMA="$(realpath -m "${SCHEMA}")"
fi

# ---------------------------
# Subcommand: validate
# ---------------------------
do_validate() {
  local alerts="$1"
  local schema="$2"
  if [[ ! -f "${alerts}" ]]; then
    echo "Alerts file not found: ${alerts}" >&2
    exit 3
  fi
  if [[ ! -f "${schema}" ]]; then
    echo "Schema file not found: ${schema}" >&2
    exit 3
  fi

  echo "[obs] Validating ${alerts} against ${schema}..."
  if has_cmd ajv; then
    if ajv validate --spec=draft2020 -s "${schema}" -d "${alerts}" >/dev/null 2>&1; then
      echo "[obs] VALID (ajv)"
      exit 0
    else
      echo "[obs] INVALID (ajv) — see details below:"
      ajv validate --spec=draft2020 -s "${schema}" -d "${alerts}" || true
      exit 4
    fi
  else
    if ! has_cmd jq; then
      echo "[obs] Neither 'ajv' nor 'jq' found. Install ajv (npm i -g ajv-cli) or jq." >&2
      exit 5
    fi
    if jq -e '
      (.version|type=="number") and (.version|floor==.) and
      (.rules|type=="array") and
      (
        reduce ((.rules // [])[]) as $r (true;
          . and
          ($r|has("id") and ($r.id|type=="string")) and
          ($r|has("severity") and ($r.severity|type=="string") and ((["CRIT","WARN","INFO"] | index($r.severity)) != null)) and
          ($r|has("window") and ($r.window|type=="string")) and
          ($r|has("description") and ($r.description|type=="string")) and
          ($r|has("metric") and ($r.metric|type=="object") and
             (($r.metric|length) >= 1) and
             (([$r.metric[] | select(type=="string")] | length) == ($r.metric|length))
          ) and
          ($r|has("expression") and ($r.expression|type=="string")) and
          (
            ($r|has("hints")|not) or
            ($r.hints|type=="array" and
              (([$r.hints[]? | select(type=="string")] | length) == ($r.hints|length))
            )
          )
        )
      )
    ' "${alerts}" >/dev/null; then
      echo "[obs] VALID (jq structural checks)"
      echo "[obs] Note: jq fallback cannot enforce additionalProperties:false; use ajv for full validation."
      exit 0
    else
      echo "[obs] INVALID (jq structural checks)" >&2
      exit 6
    fi
  fi
}

# ---------------------------
# Subcommand: check (evaluate rules)
# ---------------------------
fetch_stats() {
  local src="$1"
  if [[ -z "${src}" ]]; then
    echo "[obs] ERROR: --source requis pour 'check' (ex: http://127.0.0.1:8000/debug/eotp-stats)" >&2
    exit 7
  fi
  if [[ "${src}" == http://* || "${src}" == https://* ]]; then
    if ! has_cmd curl; then
      echo "[obs] ERROR: curl absent, impossible de récupérer ${src}" >&2
      exit 8
    fi
    curl -fsSL --max-time 5 "${src}" || {
      echo "[obs] ERROR: échec GET ${src}" >&2
      exit 8
    }
  else
    local p="$(realpath -m "${src}")"
    if [[ ! -f "${p}" ]]; then
      echo "[obs] ERROR: fichier stats introuvable: ${p}" >&2
      exit 8
    fi
    cat "${p}"
  fi
}

# Safe evaluator via Python/AST: supports + - * /, (), min(), max(), variables (a..z,0-9,_)
# "rate(x)" est réécrit en "x"
py_eval_expr() {
  local expr="$1"
  local vars_json="$2"
  python3 - <<'PYCODE' "$expr" "$vars_json"
import ast, operator, json, sys, math, re

expr = sys.argv[1]
vars_json = sys.argv[2]
# Replace rate(name) -> name
expr = re.sub(r"rate\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", r"\1", expr)
# Whitelist tokenizer by parsing AST
allowed_nodes = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq,
    ast.BoolOp, ast.And, ast.Or, ast.Assign, ast.IfExp, ast.Tuple, ast.List, ast.Dict, ast.Subscript, ast.Index, ast.Slice, ast.FloorDiv,
)
safe_funcs = {"min": min, "max": max}
vars_map = json.loads(vars_json)

def _safe(node):
    if not isinstance(node, allowed_nodes):
        raise ValueError(f"Node not allowed: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _safe(child)

try:
    tree = ast.parse(expr, mode="eval")
    _safe(tree)
    # Only allow names from vars_map and safe funcs
    class NameCheck(ast.NodeVisitor):
        def visit_Name(self, node):
            if node.id not in vars_map and node.id not in safe_funcs:
                raise NameError(f"Unknown identifier: {node.id}")
    NameCheck().visit(tree)

    compiled = compile(tree, "<expr>", "eval")
    result = eval(compiled, {"__builtins__": {}}, {**safe_funcs, **vars_map})
    # Output boolean and numeric result (if applicable)
    if isinstance(result, (int, float, bool)):
        print(json.dumps({"ok": bool(result), "val": float(result) if not isinstance(result, bool) else (1.0 if result else 0.0)}))
    else:
        print(json.dumps({"ok": False, "val": 0.0}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(9)
PYCODE
}

do_check() {
  local alerts="$1"
  local source="$2"

  if [[ ! -f "${alerts}" ]]; then
    echo "[obs] ERROR: alerts not found: ${alerts}" >&2
    exit 3
  fi

  # Load stats
  local stats_json
  stats_json="$(fetch_stats "${source}")" || exit $?
  if [[ "${PRINT_JSON}" == "1" ]]; then
    echo "[obs] stats: ${stats_json}"
  fi

  # Extract counters map
  if ! has_cmd jq; then
    echo "[obs] ERROR: jq requis pour 'check'." >&2
    exit 5
  fi

  local ok_flag
  ok_flag="$(jq -r '(.ok // .OK // .status=="ok")' <<<"${stats_json}" 2>/dev/null || true)"
  # Accept both shapes: {ok:true,stats:{...}} or raw stats object
  local counters_json
  if [[ "${ok_flag}" == "true" || "${ok_flag}" == "True" ]]; then
    counters_json="$(jq -c '.stats.counters // {}' <<<"${stats_json}")"
  else
    counters_json="$(jq -c '.counters // {}' <<<"${stats_json}")"
  fi

  # Iterate rules
  local rules_count
  rules_count="$(jq '.rules | length' "${alerts}")"
  echo "[obs] Evaluating ${rules_count} rule(s) using approximate counters..."

  local i=0
  local exit_code=0
  while [[ $i -lt ${rules_count} ]]; do
    # Extract rule fields
    local rid severity window expr metric_map
    rid="$(jq -r ".rules[$i].id" "${alerts}")"
    severity="$(jq -r ".rules[$i].severity" "${alerts}")"
    window="$(jq -r ".rules[$i].window" "${alerts}")"
    expr="$(jq -r ".rules[$i].expression" "${alerts}")"
    metric_map="$(jq -c ".rules[$i].metric" "${alerts}")"

    # Build vars from counters using rule.metric mapping
    # Example: {"ok":"eotp_ok_total","issue":"eotp_issue_total"} -> {"ok": 123, "issue": 456}
    local vars_json
    vars_json="$(jq -c --argjson counters "${counters_json}" --argjson mp "${metric_map}" '
      reduce (mp | to_entries)[] as $e ({}; .[$e.key] = ($counters[$e.value] // 0))
    ' <<<"{}")"

    # Evaluate expression safely via Python/AST (rate(x) -> x; supports min/max)
    local result_json
    result_json="$(py_eval_expr "${expr}" "${vars_json}")" || result_json='{"ok":false,"val":0}'
    local ok eval_val
    ok="$(jq -r '.ok' <<<"${result_json}" 2>/dev/null || echo false)"
    eval_val="$(jq -r '.val' <<<"${result_json}" 2>/dev/null || echo 0)"

    # Render outcome
    if [[ "${ok}" == "true" ]]; then
      # Expression true => alerte active
      echo "${severity} id=${rid} window=${window} expr='${expr}' vars=${vars_json} => TRIGGER"
      # Non-zero exit if CRIT detected; WARN keeps zero exit to allow pipelines
      if [[ "${severity}" == "CRIT" ]]; then
        exit_code=10
      fi
    else
      echo "OK   id=${rid} window=${window} expr='${expr}' vars=${vars_json}"
    fi
    i=$((i+1))
  done

  exit ${exit_code}
}

# Dispatch
case "${SUBCOMMAND}" in
  validate)
    do_validate "${ALERTS}" "${SCHEMA}"
    ;;
  check)
    do_check "${ALERTS}" "${SOURCE}"
    ;;
  *)
    echo "Unsupported subcommand: ${SUBCOMMAND}" >&2
    usage
    exit 2
    ;;
esac
