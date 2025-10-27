#!/usr/bin/env bash
#
# uninstall.sh
# Usuwa instalację cpu-fan-controller utworzoną przez install.sh
#
set -euo pipefail

TARGET_DIR="/opt/cpu-fan-controller"
LAUNCHER="/usr/local/bin/cpu-fan-controller"
SYSTEMD_SERVICE="/etc/systemd/system/cpu-fan-controller.service"
AUTOSTART_DESKTOP="/etc/xdg/autostart/cpu-fan-controller.desktop"
SYSTEM_PROFILES_DIR="/etc/cpu-fan-controller"

if [ "$EUID" -ne 0 ]; then
  echo "Uruchom jako root:"
  echo " sudo bash uninstall.sh"
  exit 1
fi

echo "[INFO] Zatrzymywanie usługi systemd (jeśli istnieje)..."
systemctl stop cpu-fan-controller.service >/dev/null 2>&1 || true
systemctl disable cpu-fan-controller.service >/dev/null 2>&1 || true
rm -f "${SYSTEMD_SERVICE}" || true
systemctl daemon-reload || true

echo "[INFO] Usuwam launcher: ${LAUNCHER}"
rm -f "${LAUNCHER}" || true

echo "[INFO] Usuwam autostart: ${AUTOSTART_DESKTOP}"
rm -f "${AUTOSTART_DESKTOP}" || true

echo "[INFO] Usuwam katalog instalacyjny: ${TARGET_DIR}"
rm -rf "${TARGET_DIR}" || true

echo "[INFO] Usuwam katalog systemowy profili: ${SYSTEM_PROFILES_DIR}"
rm -rf "${SYSTEM_PROFILES_DIR}" || true

echo "[INFO] Deinstalacja zakończona."
exit 0