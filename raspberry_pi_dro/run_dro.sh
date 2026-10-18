#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    echo "Python environment not found. Follow the Dell setup steps in README.md." >&2
    exit 1
fi

exec "${PYTHON}" "${ROOT_DIR}/lathe_dro_pro.py" "$@"