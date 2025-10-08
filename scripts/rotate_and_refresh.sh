#!/usr/bin/env bash
#
# rotate_and_refresh.sh — Orchestrate RS256 key rotation and prove refresh across rotation in CI.
#
# This script is a CI-friendly stub that:
#  1) Obtains an access+refresh pair (signed by the current/OLD key).
#  2) Triggers a rotation (deploys a NEW RS256 key and updates JWKS to publish both OLD+NEW kids).
#  3) Proves that /token/refresh with the OLD refresh works during the overlap (multi-kid JWKS).
#  4) Triggers retirement of the OLD key (JWKS goes back to a single kid: NEW).
#  5) Proves that refreshing again works under the NEW key/JWKS.
#
# It fails fast on any unexpected condition and prints a short JSON summary on success.
#
# Requirements:
#  - curl, jq, awk, sed; optional: uuidgen
#  - The API must expose:
#    - POST /api/auth/token/         (SimpleJWT obtain)      → { access, refresh }
#    - POST /api/auth/token/refresh/ (SimpleJWT refresh)     → { access }
#    - GET  /.well-known/jwks.json   (JWKS for the realm)    → { keys: [ { kid, kty:RSA, alg:RS256, n, e }, ... ] }
#
# Rotation hooks (pluggable):
#  - ROTATE_CMD: a command to deploy the NEW key + KID and publish a JWKS with OLD+NEW (overlap window)
#  - RETIRE_CMD: a command to remove OLD from JWKS (leaving NEW only)
#    These can be shell snippets (kubectl rollout, compose restart, env switch, etc.). They must block
#    until deployment is live or the script will poll JWKS until it detects the expected state.
#
# Environment variables (override as needed):
#  BASE_URL         Base URL of the realm (default: https://clients.pixelprowlers.studio)
#  TOKEN_URL        Defaults to ${BASE_URL}/api/auth/token/
#  REFRESH_URL      Defaults to ${BASE_URL}/api/auth/token/refresh/
#  JWKS_URL         Defaults to ${BASE_URL}/.well-known/jwks.json
#  USERNAME         Username for SimpleJWT (obtain)
#  PASSWORD         Password for SimpleJWT (obtain)
#  INSECURE         1 to skip TLS verification for curl (self-signed in CI), default 0
#  TIMEOUT          Per-request timeout seconds (default 10)
#  RETRIES          Poll retries for JWKS changes (default 60)
#  SLEEP_SECONDS    Delay between JWKS polls (default 1)
#  ROTATE_CMD       Command to rotate keys (deploy NEW & publish OLD+NEW JWKS), optional
#  RETIRE_CMD       Command to retire OLD key (publish NEW-only JWKS), optional
#
# Example (GitHub Actions step):
#   env:
#     BASE_URL: https://clients.local
#     USERNAME: ci_user
#     PASSWORD: ci_pass
#     INSECURE: 1
#     ROTATE_CMD: "python backend/manage.py rotate_jwt_keys --realm clients --out-dir ./secrets --jwks-out ./secrets/jwks.json && ./scripts/deploy_new_keys.sh"
#     RETIRE_CMD: "./scripts/retire_old_key.sh"
#   run: bash scripts/rotate_and_refresh.sh
#

set -Eeuo pipefail

[[ "${DEBUG:-0}" == "1" ]] && set -x

# --- Configuration
BASE_URL="${BASE_URL:-https://clients.pixelprowlers.studio}"
TOKEN_URL="${TOKEN_URL:-$BASE_URL/api/auth/token/}"
REFRESH_URL="${REFRESH_URL:-$BASE_URL/api/auth/token/refresh/}"
JWKS_URL="${JWKS_URL:-$BASE_URL/.well-known/jwks.json}"

USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"

INSECURE="${INSECURE:-0}"
TIMEOUT="${TIMEOUT:-10}"
RETRIES="${RETRIES:-60}"
SLEEP_SECONDS="${SLEEP_SECONDS:-1}"

ROTATE_CMD="${ROTATE_CMD:-}"  # optional
RETIRE_CMD="${RETIRE_CMD:-}"  # optional

CURL_FLAGS=()
if [[ "$INSECURE" == "1" ]]; then
  CURL_FLAGS+=("-k")
fi

# --- Utilities
log() { printf -- "%s\n" "$*" >&2; }
ok()  { printf -- "\033[32m[OK]\033[0m %s\n" "$*"; }
warn(){ printf -- "\033[33m[!]\033[0m %s\n" "$*"; }
die() { printf -- "\033[31m[ERR]\033[0m %s\n" "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

uuid() {
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen
  else
    # Fallback poor-man uuid
    date +%s%N | sha256sum | awk '{print $1}'
  fi
}

jwt_kid_from_access() {
  # Extract kid from JWT access header (base64url)
  # shellcheck disable=SC2001
  local token="$1"
  local header_b64u="${token%%.*}"
  # Transform URL-safe into standard base64 and pad
  local header_b64
  header_b64="$(echo -n "$header_b64u" | tr '_-' '/+' )"
  local pad=$(( (4 - (${#header_b64} % 4)) % 4 ))
  header_b64="${header_b64}$(printf '%*s' "$pad" '' | tr ' ' '=')"
  local header_json
  header_json="$(echo -n "$header_b64" | base64 -d 2>/dev/null || true)"
  if [[ -z "$header_json" ]]; then
    echo ""
    return 0
  fi
  echo "$header_json" | jq -r '(.kid // "")'
}

http_json() {
  # Usage: http_json METHOD URL [JSON_BODY]
  local method="$1"; shift
  local url="$1"; shift
  local body="${1:-}"
  local cid; cid="$(uuid)"
  if [[ -n "$body" ]]; then
    curl -fsS "${CURL_FLAGS[@]}" -X "$method" -m "$TIMEOUT" \
      -H "Content-Type: application/json" \
      -H "X-Correlation-ID: $cid" \
      --data "$body" \
      "$url"
  else
    curl -fsS "${CURL_FLAGS[@]}" -X "$method" -m "$TIMEOUT" \
      -H "X-Correlation-ID: $cid" \
      "$url"
  fi
}

get_jwks_kids() {
  local json
  json="$(http_json GET "$JWKS_URL" || true)"
  if [[ -z "$json" ]]; then
    echo ""
    return 0
  fi
  echo "$json" | jq -r '.keys[]?.kid' 2>/dev/null | sed '/^null$/d' || true
}

kids_to_set() {
  # normalize newline-separated -> space-separated sorted unique
  tr '\n' ' ' | awk '{$1=$1};1' | tr ' ' '\n' | sort -u | tr '\n' ' ' | awk '{$1=$1};1'
}

poll_for_jwks_two_keys_with_new() {
  local initial_kids="$1"
  local attempt=0
  local initial_set
  initial_set="$(echo "$initial_kids" | kids_to_set)"
  while (( attempt < RETRIES )); do
    sleep "$SLEEP_SECONDS"
    attempt=$((attempt+1))
    local kids
    kids="$(get_jwks_kids)"
    local current_set
    current_set="$(echo "$kids" | kids_to_set)"
    # Count current kids
    local count
    count="$(echo "$current_set" | awk '{print NF}')"
    if (( count >= 2 )); then
      # Detect new kid(s)
      local new=""
      for k in $current_set; do
        local found=0
        for i in $initial_set; do
          if [[ "$k" == "$i" ]]; then found=1; break; fi
        done
        if (( found == 0 )); then new="$k"; break; fi
      done
      if [[ -n "$new" ]]; then
        echo "$new"
        return 0
      fi
    fi
  done
  echo ""
  return 1
}

poll_for_jwks_one_key_matching() {
  local expected="$1"
  local attempt=0
  while (( attempt < RETRIES )); do
    sleep "$SLEEP_SECONDS"
    attempt=$((attempt+1))
    local kids
    kids="$(get_jwks_kids)"
    local set
    set="$(echo "$kids" | kids_to_set)"
    local count
    count="$(echo "$set" | awk '{print NF}')"
    if (( count == 1 )); then
      local only
      only="$(echo "$set" | awk '{print $1}')"
      if [[ "$only" == "$expected" ]]; then
        echo "$only"
        return 0
      fi
    fi
  done
  echo ""
  return 1
}

# --- Preconditions
require_cmd curl
require_cmd jq
require_cmd awk
require_cmd sed
require_cmd base64

[[ -n "$USERNAME" ]] || die "USERNAME is required"
[[ -n "$PASSWORD" ]] || die "PASSWORD is required"

log "[i] Base URL:          $BASE_URL"
log "[i] Token URL:         $TOKEN_URL"
log "[i] Refresh URL:       $REFRESH_URL"
log "[i] JWKS URL:          $JWKS_URL"
log "[i] INSECURE TLS:      $INSECURE"
log "[i] TIMEOUT/RETRIES:   ${TIMEOUT}s / ${RETRIES} polls"

# --- 1) Obtain initial access+refresh (OLD key)
log "[i] Obtaining initial tokens (pre-rotation)..."
OBTAIN_PAYLOAD="$(jq -n --arg u "$USERNAME" --arg p "$PASSWORD" '{username:$u,password:$p}')"
OBTAIN_JSON="$(http_json POST "$TOKEN_URL" "$OBTAIN_PAYLOAD" || die "Token obtain failed")"
ACCESS_OLD="$(echo "$OBTAIN_JSON" | jq -r '.access // empty')"
REFRESH_OLD="$(echo "$OBTAIN_JSON" | jq -r '.refresh // empty')"
[[ -n "$ACCESS_OLD" && -n "$REFRESH_OLD" ]] || die "Missing access/refresh in obtain response"
KID_OLD="$(jwt_kid_from_access "$ACCESS_OLD" || true)"
[[ -n "$KID_OLD" ]] || warn "Unable to parse kid from access header (continuing)"

JWKS_BEFORE="$(get_jwks_kids || true)"
[[ -n "$JWKS_BEFORE" ]] || warn "JWKS appears empty before rotation (continuing)"
log "[i] JWKS kids before: $(echo "$JWKS_BEFORE" | kids_to_set)"

# --- 2) Trigger rotation (deploy NEW key + publish OLD+NEW JWKS)
if [[ -n "$ROTATE_CMD" ]]; then
  log "[i] Running ROTATE_CMD..."
  bash -lc "$ROTATE_CMD"
else
  warn "ROTATE_CMD not provided — expecting external system to rotate keys."
fi

log "[i] Waiting for JWKS to expose at least 2 keys and detect NEW kid..."
KID_NEW="$(poll_for_jwks_two_keys_with_new "$JWKS_BEFORE" || true)"
[[ -n "$KID_NEW" ]] || die "JWKS did not publish a NEW kid within retries"
ok "Detected NEW kid in JWKS: $KID_NEW"

# --- 3) Refresh with OLD refresh (should succeed during overlap)
log "[i] Refreshing with OLD refresh (across rotation window)..."
REFRESH_PAYLOAD="$(jq -n --arg r "$REFRESH_OLD" '{refresh:$r}')"
REFRESH_JSON_1="$(http_json POST "$REFRESH_URL" "$REFRESH_PAYLOAD" || die "Refresh across rotation failed")"
ACCESS_NEW_FROM_OLD="$(echo "$REFRESH_JSON_1" | jq -r '.access // empty')"
[[ -n "$ACCESS_NEW_FROM_OLD" ]] || die "Missing 'access' in refresh response (across rotation)"
KID_FROM_REFRESH_1="$(jwt_kid_from_access "$ACCESS_NEW_FROM_OLD" || true)"
log "[i] kid(access from refreshed OLD token) = ${KID_FROM_REFRESH_1:-unknown}"

# --- 4) Retire OLD key (publish NEW-only JWKS)
if [[ -n "$RETIRE_CMD" ]]; then
  log "[i] Running RETIRE_CMD (retire OLD key)..."
  bash -lc "$RETIRE_CMD"
else
  warn "RETIRE_CMD not provided — expecting external system to retire OLD key."
fi

log "[i] Waiting for JWKS to expose a single key matching NEW..."
KID_ONE="$(poll_for_jwks_one_key_matching "$KID_NEW" || true)"
[[ -n "$KID_ONE" ]] || die "JWKS did not converge to a single NEW kid within retries"
ok "JWKS converged to a single NEW kid: $KID_ONE"

# --- 5) Refresh again (should succeed under NEW-only JWKS)
log "[i] Refreshing again with OLD refresh (should still succeed if still valid)..."
REFRESH_JSON_2="$(http_json POST "$REFRESH_URL" "$REFRESH_PAYLOAD" || die "Refresh after retirement failed")"
ACCESS_FINAL="$(echo "$REFRESH_JSON_2" | jq -r '.access // empty')"
[[ -n "$ACCESS_FINAL" ]] || die "Missing 'access' in final refresh response"
KID_FINAL="$(jwt_kid_from_access "$ACCESS_FINAL" || true)"
ok "Final refresh succeeded (kid=${KID_FINAL:-unknown})"

# --- Summary JSON
SUMMARY="$(jq -n \
  --arg base "$BASE_URL" \
  --arg jwks "$JWKS_URL" \
  --arg kid_old "${KID_OLD:-}" \
  --arg kid_new "$KID_NEW" \
  --arg kid_final "${KID_FINAL:-}" \
  --arg before "$(echo "$JWKS_BEFORE" | kids_to_set)" \
  --arg insecure "$INSECURE" \
  '{ok:true, base:$base, jwks:$jwks, insecure:($insecure=="1"), kids_before:$before, kid_old:$kid_old, kid_new:$kid_new, kid_final:$kid_final }'
)"
echo "$SUMMARY"

ok "Rotation across refresh validated."
