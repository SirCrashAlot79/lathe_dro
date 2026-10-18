#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if command -v udevadm >/dev/null 2>&1; then
    udevadm settle --timeout=10 || true
fi

exec "${ROOT_DIR}/run_dro.sh" "$@"
