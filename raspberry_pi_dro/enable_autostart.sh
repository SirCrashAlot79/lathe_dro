#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/autostart"
DESKTOP_FILE="${AUTOSTART_DIR}/lathe-dro.desktop"

mkdir -p "${AUTOSTART_DIR}"
chmod +x "${ROOT_DIR}/start_dro.sh" "${ROOT_DIR}/run_dro.sh"

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=Lathe DRO
Comment=Start the Pico 2 lathe digital readout
Exec=/usr/bin/bash "${ROOT_DIR}/start_dro.sh"
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

printf 'Autostart enabled: %s\n' "${DESKTOP_FILE}"
printf 'Disable by removing that file and logging out/in.\n'
