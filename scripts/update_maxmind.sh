#!/usr/bin/env bash
#
# PixelProwlers Studio — MaxMind GeoLite2 Updater (ASN/City)
#
# Purpose
# - Download and update MaxMind GeoLite2 ASN and City databases atomically.
# - Keep N and N-1 archives under config/maxmind/archives/.
# - Write VERSION.txt with timestamp, edition info and file hashes.
#
# Requirements
# - Environment variable MAXMIND_LICENSE_KEY must be set (GeoLite2 account required).
# - Tools: bash, curl, tar, sha256sum (or shasum -a 256), mktemp, sed, awk, date.
#
# Usage
#   scripts/update_maxmind.sh
#
# Optional environment variables
#   DB_DIR                      Target dir (default: config/maxmind)
#   MAXMIND_LICENSE_KEY         Your MaxMind license key (required)
#   MAXMIND_EDITIONS            Space-separated editions (default: "GeoLite2-ASN GeoLite2-City")
#   CURL_FLAGS                  Extra curl flags (e.g., "-k" for self-signed test env)
#   RETAIN_ARCHIVES             Number of archives to retain (default: 2; keep N and N-1)
#
# Notes
# - This script is a stub-friendly, robust updater. It avoids partial updates by preparing
#   a staging directory then atomically switching a "current" symlink.
# - If sha256sum is not available, falls back to shasum -a 256.
# - It does NOT fetch remote checksums; it records local sha256 hashes in VERSION.txt.
#

set -Eeuo pipefail

# --- Configuration -----------------------------------------------------------------

DB_DIR="${DB_DIR:-config/maxmind}"
ARCHIVES_DIR="$DB_DIR/archives"
CURRENT_LINK="$DB_DIR/current"
RETAIN_ARCHIVES="${RETAIN_ARCHIVES:-2}"

# Editions to download (default: ASN & City)
MAXMIND_EDITIONS_DEFAULT=("GeoLite2-ASN" "GeoLite2-City")
# shellcheck disable=SC2206
MAXMIND_EDITIONS=(${MAXMIND_EDITIONS:-"${MAXMIND_EDITIONS_DEFAULT[*]}"} )

LICENSE="${MAXMIND_LICENSE_KEY:-}"

CURL_BIN="${CURL_BIN:-curl}"
CURL_FLAGS="${CURL_FLAGS:-}"
TAR_BIN="${TAR_BIN:-tar}"

# --- Helpers -----------------------------------------------------------------------

log()  { printf -- "[%s] %s\n" "$(date -u +%FT%TZ)" "$*" >&2; }
die()  { printf -- "[%s] ERROR: %s\n" "$(date -u +%FT%TZ)" "$*" >&2; exit 1; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

sha256() {
  if has_cmd sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  elif has_cmd shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "No sha256sum or shasum found in PATH."
  fi
}

mkd() { mkdir -p "$1" || die "Failed to create directory: $1"; }

atomic_mv() {
  # mv -T is not POSIX; emulate atomic replace of a symlink/dir file by 'mv' after rename
  local src="$1" dst="$2"
  mv "$src" "$dst" || die "Atomic move failed: $src -> $dst"
}

safe_rm() {
  local p="$1"
  [[ -e "$p" ]] && rm -rf -- "$p" || true
}

# Keep only the last $RETAIN_ARCHIVES archives (most recent first)
prune_archives() {
  local keep="${RETAIN_ARCHIVES:-2}"
  local archives
  # List directories sorted reverse (latest first)
  IFS=$'\n' read -r -d '' -a archives < <(ls -1dt "$ARCHIVES_DIR"/*/ 2>/dev/null || true; printf '\0')
  local count="${#archives[@]}"

  if (( count > keep )); then
    for (( i=keep; i<count; i++ )); do
      local old="${archives[$i]%/}"
      log "Pruning old archive: $old"
      safe_rm "$old"
    done
  fi
}

download_and_extract() {
  # $1 edition (e.g., GeoLite2-ASN)
  # $2 destination dir for mmdbs (staging dir)
  local edition="$1" dest="$2"
  local url="https://download.maxmind.com/geoip/databases/${edition}/download?suffix=tar.gz&license_key=${LICENSE}"

  local tmp_tar
  tmp_tar="$(mktemp -t "maxmind_${edition}.XXXXXX.tar.gz")"
  log "Downloading ${edition} ..."
  $CURL_BIN -fsSL $CURL_FLAGS -o "$tmp_tar" "$url" || die "Download failed for $edition"

  # Extract tarball to a temporary dir
  local tmp_extract
  tmp_extract="$(mktemp -d -t "maxmind_${edition}_extract.XXXXXX")"
  $TAR_BIN -xzf "$tmp_tar" -C "$tmp_extract" || die "Extract failed for $edition"

  # Find .mmdb inside extracted dir
  local mmdb
  mmdb="$(find "$tmp_extract" -type f -name "*.mmdb" | head -n1 || true)"
  [[ -f "$mmdb" ]] || die "No .mmdb found in $edition archive"

  # Copy mmdb to dest with conventional name edition.mmdb (e.g., GeoLite2-ASN.mmdb)
  local out="$dest/${edition}.mmdb"
  cp -f "$mmdb" "$out" || die "Failed to copy $edition.mmdb to staging"
  log "${edition}.mmdb -> $out"

  # cleanup
  rm -f "$tmp_tar"
  rm -rf "$tmp_extract"
}

write_version_file() {
  # $1 staging dir
  local staging="$1"
  local ts="$(date -u +%FT%TZ)"
  local ver_file="$staging/VERSION.txt"

  {
    echo "Updated at: ${ts}"
    echo "Host: $(hostname 2>/dev/null || echo unknown)"
    echo "Editions:"
    for ed in "${MAXMIND_EDITIONS[@]}"; do
      local f="$staging/${ed}.mmdb"
      if [[ -f "$f" ]]; then
        echo "  - ${ed}.mmdb  sha256=$(sha256 "$f")  size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")"
      else
        echo "  - ${ed}.mmdb  MISSING"
      fi
    done
  } > "$ver_file"
}

archive_snapshot() {
  # $1 path to current dir (resolved link) OR directory to archive
  local src_dir="$1"
  [[ -d "$src_dir" ]] || return 0

  local stamp
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  local out_dir="$ARCHIVES_DIR/$stamp"
  mkd "$out_dir"
  log "Archiving previous DB to $out_dir"
  cp -a "$src_dir/." "$out_dir/" || die "Failed to archive previous DB"
}

switch_current_atomically() {
  # $1 staging populated dir
  local staging="$1"

  # If current is a symlink to a dir, resolve it to archive safely
  local prev_dir=""
  if [[ -L "$CURRENT_LINK" ]]; then
    prev_dir="$(readlink "$CURRENT_LINK")"
    # Convert relative symlink to absolute
    [[ "$prev_dir" != /* ]] && prev_dir="$(cd "$(dirname "$CURRENT_LINK")" && cd "$(dirname "$prev_dir")" && pwd)/$(basename "$prev_dir")"
  elif [[ -d "$CURRENT_LINK" ]]; then
    prev_dir="$CURRENT_LINK"
  fi

  # Archive previous (if any)
  if [[ -n "$prev_dir" && -d "$prev_dir" ]]; then
    archive_snapshot "$prev_dir"
  fi

  # Prepare destination "release" dir and switch current symlink atomically
  local release_dir="$DB_DIR/release_$(date -u +%Y%m%d_%H%M%S)"
  mv "$staging" "$release_dir" || die "Failed to promote staging to release"
  ln -sfn "$release_dir" "$CURRENT_LINK" || die "Failed to switch current symlink"

  # Prune archives
  prune_archives

  log "Switched current -> $release_dir"
  log "VERSION: $(sed -n '1p' "$release_dir/VERSION.txt")"
}

# --- Main --------------------------------------------------------------------------

main() {
  [[ -n "$LICENSE" ]] || die "MAXMIND_LICENSE_KEY is not set."

  mkd "$DB_DIR"
  mkd "$ARCHIVES_DIR"

  # Staging dir (auto-cleaned by trap if anything fails before switch)
  local staging
  staging="$(mktemp -d -t "maxmind_staging.XXXXXX")"
  trap 'rm -rf "$staging" 2>/dev/null || true' EXIT

  # Download each requested edition
  for ed in "${MAXMIND_EDITIONS[@]}"; do
    download_and_extract "$ed" "$staging"
  done

  # VERSION.txt
  write_version_file "$staging"

  # Switch atomically
  switch_current_atomically "$staging"

  # Remove trap; keep release dir
  trap - EXIT

  # Print summary JSON
  local kids_json
  kids_json="$(jq -n \
    --arg dir "$DB_DIR" \
    --arg curr "$(readlink -f "$CURRENT_LINK" 2>/dev/null || echo "$CURRENT_LINK")" \
    --arg ts "$(date -u +%FT%TZ)" \
    '{ok:true, db_dir:$dir, current:$curr, updated_at:$ts}')"
  echo "$kids_json"
}

# jq fallback (very minimal) if jq missing
if ! has_cmd jq; then
  jq() { cat; }
fi

main "$@"
