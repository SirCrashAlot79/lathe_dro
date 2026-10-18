#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

sudo apt update
sudo apt install -y python3 python3-venv python3-pygame python3-serial
python3 -m venv --system-site-packages "${ROOT_DIR}/.venv"
chmod +x "${ROOT_DIR}/run_dro.sh" "${ROOT_DIR}/start_dro.sh" \
	"${ROOT_DIR}/enable_autostart.sh" "${ROOT_DIR}/build_pico2.sh"

"${ROOT_DIR}/.venv/bin/python" -c "import pygame, serial; print('Pygame', pygame.version.ver, '| pyserial', serial.VERSION)"
printf '\nInstall complete. Connect the Pico in normal mode and run: %s/run_dro.sh\n' "${ROOT_DIR}"
