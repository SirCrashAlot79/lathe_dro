#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PICO_SDK_PATH="${PICO_SDK_PATH:-${ROOT_DIR}/pico-sdk}"

if [[ ! -d "${PICO_SDK_PATH}/src/rp2_common" ]]; then
    echo "Pico SDK not found at ${PICO_SDK_PATH}. Set PICO_SDK_PATH or install it in the project directory." >&2
    exit 1
fi

cmake -S "${ROOT_DIR}" -B "${ROOT_DIR}/build-pico2" -G Ninja
cmake --build "${ROOT_DIR}/build-pico2" --parallel "$(nproc)"