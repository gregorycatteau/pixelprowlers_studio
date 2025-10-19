#!/usr/bin/env bash
#
# PixelProwlers Studio — xcaddy-build.sh
#
# Build a custom Caddy binary with required plugins using xcaddy.
#
# Features:
# - Defaults to include security-oriented plugins (CrowdSec bouncer, greenpau auth suite, MaxMind geolocation).
# - Works with local xcaddy if installed; otherwise tries to install xcaddy with Go.
# - Optional Docker fallback using the official xcaddy image (if Docker available).
# - Supports GOOS/GOARCH cross compilation via environment variables.
#
# Usage:
#   ./config/xcaddy-build.sh [-o out_path] [-v caddy_version] [-- no-default-plugins] [--with plugin@ver ...]
#
# Examples:
#   # Quick build with defaults for host platform
#   ./config/xcaddy-build.sh
#
#   # Specific Caddy version and output path
#   CADDY_VERSION=v2.8.4 ./config/xcaddy-build.sh -o ./bin/caddy-v2.8.4
#
#   # Cross-compile for linux/arm64 and add/remove plugins
#   GOOS=linux GOARCH=arm64 ./config/xcaddy-build.sh --with github.com/caddyserver/transform-encoder@latest
#
# Notes:
# - Ensure you comply with the licenses of Caddy and the selected plugins.
# - For reproducibility, pin plugin versions instead of using @latest.
# - After building, you can check loaded modules with: ./bin/caddy version
#

set -Eeuo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# Defaults (override via env or CLI)
# ──────────────────────────────────────────────────────────────────────────────

# Pin to a known Caddy version for reproducibility. Change as needed.
: "${CADDY_VERSION:=v2.8.4}"

# Output binary path (default depends on GOOS/GOARCH/CADDY_VERSION)
: "${GOOS:=}"
: "${GOARCH:=}"
DEFAULT_OUT_DIR="./bin"
DEFAULT_OUT_NAME="caddy-${CADDY_VERSION}${GOOS:+-$GOOS}${GOARCH:+-$GOARCH}"
OUT_PATH="${DEFAULT_OUT_DIR}/${DEFAULT_OUT_NAME}"

# Default plugin set (override with -- no-default-plugins + --with ... or via env PLUGINS)
DEFAULT_PLUGINS=(
  "github.com/crowdsecurity/caddy-crowdsec-bouncer@latest"
  "github.com/greenpau/caddy-auth-portal@latest"
  "github.com/greenpau/caddy-authorize@latest"
  "github.com/greenpau/caddy-auth-jwt@latest"
  "github.com/greenpau/caddy-security@latest"
  "github.com/porech/caddy-maxmind-geolocation@latest"
)

# Allow providing extra plugins via env PLUGINS (space-separated)
: "${PLUGINS:=}"

# Docker image for fallback builds
: "${XCADDY_DOCKER_IMAGE:=ghcr.io/caddyserver/xcaddy:latest}"

# Optional Go build flags (e.g., -trimpath -ldflags '-s -w')
: "${XCADDY_GO_BUILD_FLAGS:=-trimpath}"

# ──────────────────────────────────────────────────────────────────────────────
# CLI parsing
# ──────────────────────────────────────────────────────────────────────────────

print_help() {
  cat <<EOF
xcaddy-build.sh — Build Caddy with plugins

Usage:
  $(basename "$0") [-o out_path] [-v caddy_version] [-- no-default-plugins] [--with plugin@ver ...]

Options:
  -o, --output PATH          Output binary path (default: ${OUT_PATH})
  -v, --version VERSION      Caddy version tag (default: ${CADDY_VERSION})
      -- no-default-plugins  Do not include the default plugin set
      --with PLUGIN[@VER]    Add a plugin (can be repeated); example: --with github.com/some/plugin@v1.2.3
  -h, --help                 Show this help

Env overrides:
  CADDY_VERSION              Version tag (e.g., v2.8.4)
  GOOS, GOARCH               Cross-compilation target (e.g., GOOS=linux GOARCH=arm64)
  PLUGINS                    Additional plugins (space-separated)
  XCADDY_DOCKER_IMAGE        Docker image for fallback (default: ${XCADDY_DOCKER_IMAGE})
  XCADDY_GO_BUILD_FLAGS      Go build flags for xcaddy (default: ${XCADDY_GO_BUILD_FLAGS})

Examples:
  GOOS=linux GOARCH=arm64 CADDY_VERSION=v2.8.4 \\
    $(basename "$0") -o ./bin/caddy-linux-arm64 --with github.com/caddyserver/transform-encoder@latest
EOF
}

USE_DEFAULT_PLUGINS=1
CLI_EXTRA_PLUGINS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      OUT_PATH="$2"; shift 2;;
    -v|--version)
      CADDY_VERSION="$2"; shift 2;;
    --)
      shift
      # treat remaining tokens as flags (like no-default-plugins) or plugins
      while [[ $# -gt 0 ]]; do
        if [[ "$1" == "no-default-plugins" ]]; then
          USE_DEFAULT_PLUGINS=0
          shift
        elif [[ "$1" == "--with" ]]; then
          [[ $# -lt 2 ]] && { echo "Error: --with requires a value"; exit 2; }
          CLI_EXTRA_PLUGINS+=("$2")
          shift 2
        else
          echo "Unknown argument after --: $1"
          exit 2
        fi
      done
      ;;
    --with)
      [[ $# -lt 2 ]] && { echo "Error: --with requires a value"; exit 2; }
      CLI_EXTRA_PLUGINS+=("$2")
      shift 2;;
    --no-default-plugins|no-default-plugins)
      USE_DEFAULT_PLUGINS=0; shift;;
    -h|--help)
      print_help; exit 0;;
    *)
      echo "Unknown argument: $1"; print_help; exit 2;;
  esac
done

# Merge plugin sources
COMBINED_PLUGINS=()
if [[ "${USE_DEFAULT_PLUGINS}" -eq 1 ]]; then
  COMBINED_PLUGINS+=("${DEFAULT_PLUGINS[@]}")
fi
# from env PLUGINS (space-separated)
if [[ -n "${PLUGINS}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_FROM_ENV=(${PLUGINS})
  COMBINED_PLUGINS+=("${EXTRA_FROM_ENV[@]}")
fi
# from CLI --with
if [[ ${#CLI_EXTRA_PLUGINS[@]} -gt 0 ]]; then
  COMBINED_PLUGINS+=("${CLI_EXTRA_PLUGINS[@]}")
fi

# De-duplicate plugins while preserving order
uniq_plugins() {
  awk '!seen[$0]++'
}
COMBINED_PLUGINS=($(printf "%s\n" "${COMBINED_PLUGINS[@]}" | uniq_plugins))

# Ensure output dir exists
mkdir -p "$(dirname "${OUT_PATH}")"

echo "==> Configuration"
echo "    Caddy version   : ${CADDY_VERSION}"
echo "    Output          : ${OUT_PATH}"
echo "    GOOS/GOARCH     : ${GOOS:-host}/${GOARCH:-host}"
if [[ ${#COMBINED_PLUGINS[@]} -gt 0 ]]; then
  echo "    Plugins         :"
  for p in "${COMBINED_PLUGINS[@]}"; do echo "      - ${p}"; done
else
  echo "    Plugins         : (none)"
fi
echo

# ──────────────────────────────────────────────────────────────────────────────
# xcaddy availability (local → install via Go → Docker fallback)
# ──────────────────────────────────────────────────────────────────────────────

have_cmd() { command -v "$1" >/dev/null 2>&1; }

build_with_xcaddy() {
  local out="$1"; shift
  local caddy_version="$1"; shift
  local -a plugins=("$@")

  echo "==> Building with local xcaddy"
  local args=()
  if [[ -n "${GOOS:-}" ]]; then args+=("GOOS=${GOOS}"); fi
  if [[ -n "${GOARCH:-}" ]]; then args+=("GOARCH=${GOARCH}"); fi
  if [[ -n "${XCADDY_GO_BUILD_FLAGS:-}" ]]; then args+=("XCADDY_GO_BUILD_FLAGS=${XCADDY_GO_BUILD_FLAGS}"); fi

  # shellcheck disable=SC2068
  "${args[@]}" xcaddy build "${caddy_version}" \
    $(for p in "${plugins[@]}"; do printf -- " --with %s" "$p"; done) \
    --output "${out}"
}

build_with_go_install_then_xcaddy() {
  echo "==> Installing xcaddy via Go"
  go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
  build_with_xcaddy "$@"
}

build_with_docker_xcaddy() {
  local out="$1"; shift
  local caddy_version="$1"; shift
  local -a plugins=("$@")

  echo "==> Building with Docker: ${XCADDY_DOCKER_IMAGE}"
  # We mount the current workspace and write output to OUT_PATH
  local workdir
  workdir="$(pwd)"
  local out_abs
  out_abs="$(realpath "${out}")"

  # Compose plugin flags for the container
  local plugin_flags=()
  for p in "${plugins[@]}"; do
    plugin_flags+=(--with "$p")
  done

  docker run --rm \
    -e GOOS="${GOOS:-}" \
    -e GOARCH="${GOARCH:-}" \
    -e XCADDY_GO_BUILD_FLAGS="${XCADDY_GO_BUILD_FLAGS:-}" \
    -v "${workdir}:${workdir}" \
    -w "${workdir}" \
    "${XCADDY_DOCKER_IMAGE}" \
    build "${caddy_version}" \
      "${plugin_flags[@]}" \
      --output "${out_abs}"
}

# Dispatcher
if have_cmd xcaddy; then
  build_with_xcaddy "${OUT_PATH}" "${CADDY_VERSION}" "${COMBINED_PLUGINS[@]}"
elif have_cmd go; then
  build_with_go_install_then_xcaddy "${OUT_PATH}" "${CADDY_VERSION}" "${COMBINED_PLUGINS[@]}"
elif have_cmd docker; then
  build_with_docker_xcaddy "${OUT_PATH}" "${CADDY_VERSION}" "${COMBINED_PLUGINS[@]}"
else
  echo "Error: Neither xcaddy nor go nor docker is available on PATH. Cannot build." >&2
  exit 1
fi

echo
echo "==> Build complete: ${OUT_PATH}"
echo "    File size: $(stat -c%s "${OUT_PATH}" 2>/dev/null || stat -f%z "${OUT_PATH}") bytes"
echo

# ──────────────────────────────────────────────────────────────────────────────
# Post-build: show version (modules should be listed)
# ──────────────────────────────────────────────────────────────────────────────

if [[ -x "${OUT_PATH}" ]]; then
  echo "==> Caddy version info:"
  "${OUT_PATH}" version || true
  echo
  echo "Tip: make it executable if needed: chmod +x ${OUT_PATH}"
else
  # On some OS, execute bit may not be set; try to set it.
  chmod +x "${OUT_PATH}" 2>/dev/null || true
  if [[ -x "${OUT_PATH}" ]]; then
    "${OUT_PATH}" version || true
  fi
fi

echo "Done."
