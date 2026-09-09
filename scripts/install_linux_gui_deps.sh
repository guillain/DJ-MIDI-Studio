#!/usr/bin/env bash
# Install the system libraries the PySide6 GUI and python-rtmidi need on a
# Linux CI runner, resiliently.
#
# GitHub's hosted runner images preconfigure several third-party apt repos
# (Google Chrome, Microsoft, Google Cloud SDK, ...). When one of those serves
# stale or corrupt index metadata, a plain "apt-get update" aborts the whole
# job with "Hash Sum mismatch" / "Failed to fetch" even though none of those
# repos provide anything this project needs. Drop every non-Ubuntu apt source
# before updating, and retry for ordinary network flakiness.
set -euo pipefail

PACKAGES=(
  libasound2-dev
  pkg-config
  libegl1
  libgl1
  libxkbcommon0
  libxkbcommon-x11-0
)

# Keep only the base Ubuntu archive definition; remove preinstalled vendor
# repos that we never pull from and that are the usual source of flakes.
sudo find /etc/apt/sources.list.d -type f ! -name 'ubuntu.sources' -print -delete || true

retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if "$@"; then
      return 0
    fi
    if [[ "${attempt}" -eq 5 ]]; then
      echo "Command failed after ${attempt} attempts: $*" >&2
      return 1
    fi
    echo "Command failed (attempt ${attempt}); retrying in 10s: $*" >&2
    sleep 10
  done
}

retry sudo apt-get update
retry sudo apt-get install -y "${PACKAGES[@]}"
