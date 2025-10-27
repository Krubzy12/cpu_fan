#!/usr/bin/env bash
#
# install.sh
# Uniwersalny instalator projektu "cpu-fan-controller" (instalacja system-wide)
#
# Uruchom jako root:
#   sudo bash install.sh
#
set -euo pipefail

TARGET_DIR="/opt/cpu-fan-controller"
VENV_DIR="${TARGET_DIR}/venv"
SRC_DIR="$(pwd)"
LAUNCHER="/usr/local/bin/cpu-fan-controller"
SYSTEM_PROFILES_DIR="/etc/cpu-fan-controller/profiles"
SYSTEMD_SERVICE="/etc/systemd/system/cpu-fan-controller.service"
AUTOSTART_DESKTOP="/etc/xdg/autostart/cpu-fan-controller.desktop"

info() { echo -e "\e[34m[INFO]\e[0m $*"; }
warn() { echo -e "\e[33m[WARN]\e[0m $*"; }
err()  { echo -e "\e[31m[ERROR]\e[0m $*" >&2; }

if [ "$EUID" -ne 0 ]; then
  echo "Ten skrypt wymaga uprawnień root. Uruchom go przez sudo:"
  echo "  sudo bash install.sh"
  exit 1
fi

info "Instalacja cpu-fan-controller do: ${TARGET_DIR}"
info "Katalog źródłowy: ${SRC_DIR}"

# Wykryj menedżera pakietów
PKG_INSTALL_CMD=""
if command -v apt >/dev/null 2>&1; then
  PKG_INSTALL_CMD="apt-get install -y"
  info "Wykryto apt. Użyję apt do instalacji pakietów systemowych."
elif command -v dnf >/dev/null 2>&1; then
  PKG_INSTALL_CMD="dnf install -y"
  info "Wykryto dnf. Użyję dnf do instalacji pakietów systemowych."
else
  warn "Nie wykryto apt/dnf. Zainstaluj ręcznie: python3, python3-venv, python3-pip, lm-sensors."
fi

# 1) kopiowanie plików
info "Kopiowanie plików projektu do ${TARGET_DIR}..."
rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
rsync -a --exclude 'venv' --exclude '__pycache__' --exclude '.git' "${SRC_DIR}/" "${TARGET_DIR}/"

# 2) instalacja pakietów systemowych
if [ -n "${PKG_INSTALL_CMD}" ]; then
  if command -v apt >/dev/null 2>&1; then
    info "Aktualizacja list pakietów..."
    apt-get update -y
  fi
  PACKAGES="python3 python3-venv python3-pip lm-sensors rsync"
  info "Instaluję pakiety: ${PACKAGES}"
  ${PKG_INSTALL_CMD} ${PACKAGES}
else
  warn "Pominięto instalację pakietów systemowych."
fi

# 3) stwórz virtualenv i zainstaluj pip requirements
info "Tworzę virtualenv w: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
if [ -f "${TARGET_DIR}/requirements.txt" ]; then
  info "Instaluję zależności pip z requirements.txt"
  "${VENV_DIR}/bin/pip" install -r "${TARGET_DIR}/requirements.txt"
else
  warn "Brak requirements.txt w katalogu projektu."
fi

# 4) Utwórz katalog systemowy z profilami i skopiuj przykładowe profile, jeśli istnieją
info "Tworzę katalog systemowy profili: ${SYSTEM_PROFILES_DIR}"
mkdir -p "${SYSTEM_PROFILES_DIR}"
chmod 755 /etc/cpu-fan-controller || true
chmod 755 "${SYSTEM_PROFILES_DIR}" || true
if [ -d "${TARGET_DIR}/profiles" ]; then
  rsync -a "${TARGET_DIR}/profiles/" "${SYSTEM_PROFILES_DIR}/" || true
fi

# 5) stwórz launcher w /usr/local/bin
info "Tworzę launcher: ${LAUNCHER}"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Launcher uruchamiający GUI z virtualenv
TARGET_DIR="${TARGET_DIR}"
VENV="${VENV_DIR}"
if [ ! -d "\${VENV}" ]; then
  echo "Brak virtualenv w \${VENV}. Uruchom instalator."
  exit 1
fi
exec "\${VENV}/bin/python" "\${TARGET_DIR}/main.py" "\$@"
EOF
chmod +x "${LAUNCHER}"

# 6) utwórz plik autostartu dla wszystkich użytkowników (xdg autostart)
info "Tworzę plik autostartu: ${AUTOSTART_DESKTOP}"
cat > "${AUTOSTART_DESKTOP}" <<EOF
[Desktop Entry]
Type=Application
Name=CPU Monitor & Fan Controller
Exec=${LAUNCHER}
Terminal=false
X-GNOME-Autostart-enabled=true
Comment=Monitor CPU i kontrola wentylatorów
EOF
chmod 644 "${AUTOSTART_DESKTOP}"

# 7) stwórz przykładową jednostkę systemd (opcjonalna, jeśli chcesz uruchamiać w tle jako root)
info "Tworzę jednostkę systemd: ${SYSTEMD_SERVICE}"
cat > "${SYSTEMD_SERVICE}" <<EOF
[Unit]
Description=CPU Monitor & Fan Controller (system-wide service - optional)
After=multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=${TARGET_DIR}
ExecStart=${VENV_DIR}/bin/python ${TARGET_DIR}/main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "${SYSTEMD_SERVICE}"
systemctl daemon-reload || true

info "Instalacja zakończona."
echo "Pliki zainstalowano w ${TARGET_DIR}. Launcher dostępny jako ${LAUNCHER}."
echo "Profile globalne: ${SYSTEM_PROFILES_DIR}  (możesz dodać tam pliki .json by udostępnić profile wszystkim użytkownikom)."
echo "Autostart dla wszystkich użytkowników utworzono w: ${AUTOSTART_DESKTOP}"
echo "Aby uruchomić GUI jako bieżący użytkownik, po prostu wpisz: cpu-fan-controller"
echo
echo "Jeśli chcesz uruchamiać usługę systemową (jako root), włącz ją:"
echo "  sudo systemctl enable --now cpu-fan-controller.service"
echo
exit 0