#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Install to /opt/picar-px to avoid noexec /home filesystem issues on some Pi setups.
# If cloned directly into /opt/picar-px already, stay there.
if [[ "$SOURCE_DIR" == /opt/picar-px ]]; then
  PROJECT_DIR="/opt/picar-px"
else
  PROJECT_DIR="/opt/picar-px"
  if [[ ! -d "$PROJECT_DIR" ]]; then
    mkdir -p "$PROJECT_DIR"
    cp -r "$SOURCE_DIR/." "$PROJECT_DIR/"
  fi
fi
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE_FILE="$PROJECT_DIR/.env.example"
SERVICE_NAME="picarx-unified.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

INSTALL_DEPS=1
RUN_APP=1
START_SERVICE=0
MOCK_MODE=0
SKIP_SUNFOUNDER=0
INSTALL_SERVICE=1
HOST_OVERRIDE=""
PORT_OVERRIDE=""

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\n[ERROR] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
PiCar-X Unified one-file Raspberry Pi bootstrapper.

Usage:
  bash scripts/install_pi.sh [options]

What it does by default:
  1. Installs required Raspberry Pi OS packages
  2. Installs the official SunFounder PiCar-X Python stack if needed
  3. Creates/updates the local virtual environment
  4. Copies .env.example to .env on first run
  5. Installs/enables a path-correct systemd service
  6. Launches the app

Options:
  --install-only        Install everything but do not start the app
  --service             Install/update and start the systemd service instead of a foreground app
  --run-only            Skip installation and just run the app
  --mock                Run in mock hardware/camera mode
  --no-service          Do not install or update the systemd service
  --skip-sunfounder     Do not auto-install the official SunFounder stack
  --host HOST           Override PICARX_HOST for this run
  --port PORT           Override PICARX_PORT for this run
  --help                Show this message

Examples:
  bash scripts/install_pi.sh
  bash scripts/install_pi.sh --mock
  bash scripts/install_pi.sh --install-only
  bash scripts/install_pi.sh --service
  bash scripts/install_pi.sh --run-only --host 0.0.0.0 --port 8080
EOF
}

while (($# > 0)); do
  case "$1" in
    --install-only)
      RUN_APP=0
      ;;
    --service)
      RUN_APP=0
      START_SERVICE=1
      ;;
    --run-only)
      INSTALL_DEPS=0
      ;;
    --mock)
      MOCK_MODE=1
      ;;
    --no-service)
      INSTALL_SERVICE=0
      ;;
    --skip-sunfounder)
      SKIP_SUNFOUNDER=1
      ;;
    --host)
      shift
      HOST_OVERRIDE="${1:-}"
      [[ -n "$HOST_OVERRIDE" ]] || fail "--host requires a value"
      ;;
    --port)
      shift
      PORT_OVERRIDE="${1:-}"
      [[ -n "$PORT_OVERRIDE" ]] || fail "--port requires a value"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
  shift
done

run_root() {
  "${SUDO[@]}" "$@"
}

python_has_module() {
  local module_name="$1"
  python3 - "$module_name" <<'PY'
import importlib.util
import sys

module = sys.argv[1]
raise SystemExit(0 if importlib.util.find_spec(module) else 1)
PY
}

venv_pip() {
  "$VENV_DIR/bin/python" -m pip "$@"
}

install_system_packages() {
  log "Installing Raspberry Pi OS packages"
  run_root apt update
  run_root apt install -y \
    git \
    python3 \
    python3-venv \
    python3-pip \
    libcamera-ipa \
    libcamera0.3 \
    python3-libcamera \
    python3-opencv \
    python3-picamera2 \
    rpicam-apps-lite \
    espeak-ng \
    alsa-utils \
    avahi-daemon \
    openssl \
    aircrack-ng \
    samba

  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl enable --now avahi-daemon || true
  fi
}

install_samba_netbios() {
  command -v nmbd >/dev/null 2>&1 || return

  local host_name
  host_name="$(hostname 2>/dev/null || printf 'picarx')"

  local smb_conf="/etc/samba/smb.conf"
  [[ -f "$smb_conf" ]] || return

  # Only write once — skip if already configured by us
  if grep -q 'wins support = yes' "$smb_conf" 2>/dev/null; then
    log "Samba NetBIOS already configured"
  else
    log "Configuring Samba for Windows NetBIOS name resolution"
    cat >> "$smb_conf" <<EOF

# PiCar-X: advertise hostname to Windows via NetBIOS (no client setup needed)
[global]
   netbios name = ${host_name^^}
   workgroup = WORKGROUP
   server role = standalone server
   wins support = yes
   dns proxy = no
EOF
  fi

  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl enable --now smbd nmbd || true
    run_root systemctl restart nmbd || true
  fi
}

install_sunfounder_stack() {
  if (( MOCK_MODE )) || (( SKIP_SUNFOUNDER )); then
    return
  fi

  if python_has_module "picarx"; then
    log "Official SunFounder PiCar-X Python stack already installed"
    return
  fi

  log "Installing official SunFounder PiCar-X Python stack"
  local tmp_dir
  tmp_dir="$(mktemp -d /tmp/picarx-unified-sunfounder-XXXXXX)"

  git clone --depth 1 -b v2.0 https://github.com/SunFounder/picar-x.git "$tmp_dir"
  (
    cd "$tmp_dir"
    run_root python3 setup.py install
  )
  rm -rf "$tmp_dir"

  if ! python_has_module "picarx"; then
    fail "SunFounder PiCar-X stack installation finished but the 'picarx' module is still unavailable."
  fi

  log "Installing SunFounder robot-hat library"
  local rh_dir
  rh_dir="$(mktemp -d /tmp/picarx-unified-robot-hat-XXXXXX)"
  git clone --depth 1 https://github.com/sunfounder/robot-hat.git "$rh_dir"
  (
    cd "$rh_dir"
    run_root python3 setup.py install
  )
  rm -rf "$rh_dir"
}

ensure_virtualenv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment"
    python3 -m venv --system-site-packages "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  log "Installing Python package without replacing Raspberry Pi camera packages"
  venv_pip install --upgrade pip setuptools wheel
  venv_pip install \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "filelock>=3.16.1" \
    "pydantic>=2.9.0" \
    "google-genai>=1.72.0"
  # Uninstall venv-installed numpy/opencv/simplejpeg before installing the project
  # so we don't get binary incompatibility with the system picamera2/simplejpeg.
  venv_pip uninstall -y \
    numpy \
    opencv-python \
    opencv-python-headless \
    opencv-contrib-python \
    simplejpeg >/dev/null 2>&1 || true
  # Rebuild simplejpeg from source to match the system numpy version (avoids binary incompatibility)
  venv_pip install simplejpeg --no-binary simplejpeg
  # Install the project package (non-editable so it works under systemd without PYTHONPATH tricks)
  venv_pip install "$PROJECT_DIR"
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]] || [[ ! -f "$ENV_EXAMPLE_FILE" ]]; then
    return
  fi

  log "Creating .env from .env.example"
  cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
}

ensure_env_default() {
  local key="$1"
  local value="$2"
  if [[ ! -f "$ENV_FILE" ]]; then
    return
  fi
  if grep -qE "^${key}=" "$ENV_FILE"; then
    return
  fi
  printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
}

ensure_env_defaults() {
  ensure_env_default "PICARX_HOST" "0.0.0.0"
  ensure_env_default "PICARX_PORT" "8080"
  ensure_env_default "PICARX_USE_MOCK" "false"
  ensure_env_default "PICARX_HARDWARE_INIT_MODE" "direct"
  ensure_env_default "PICARX_HTTPS_ENABLE" "true"
  ensure_env_default "PICARX_SSL_CERTFILE" "certs/picarx.crt"
  ensure_env_default "PICARX_SSL_KEYFILE" "certs/picarx.key"
}

load_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    return
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue

    local key="${line%%=*}"
    local value="${line#*=}"

    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    if [[ "$value" =~ ^\".*\"$ || "$value" =~ ^\'.*\'$ ]]; then
      value="${value:1:-1}"
    fi

    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$ENV_FILE"
}

absolute_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s/%s\n' "$PROJECT_DIR" "$path"
  fi
}

ensure_https_certificate() {
  local https_requested="${PICARX_HTTPS_ENABLE:-false}"
  case "${https_requested,,}" in
    1|true|yes|on) ;;
    *) return ;;
  esac

  local certfile="${PICARX_SSL_CERTFILE:-certs/picarx.crt}"
  local keyfile="${PICARX_SSL_KEYFILE:-certs/picarx.key}"
  [[ -n "$certfile" && -n "$keyfile" ]] || return

  certfile="$(absolute_path "$certfile")"
  keyfile="$(absolute_path "$keyfile")"
  if [[ -f "$certfile" && -f "$keyfile" ]]; then
    return
  fi

  command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate HTTPS certificates"

  log "Generating self-signed HTTPS certificate"
  run_root mkdir -p "$(dirname "$certfile")" "$(dirname "$keyfile")"

  local host_name
  host_name="$(hostname 2>/dev/null || printf 'picarx')"

  local openssl_config
  openssl_config="$(mktemp /tmp/picarx-unified-openssl-XXXXXX.cnf)"
  cat > "$openssl_config" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no

[dn]
CN = picarx.local

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = picarx.local
DNS.2 = $host_name
DNS.3 = ${host_name}.local
DNS.4 = picarx
IP.1 = 127.0.0.1
EOF

  run_root openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$keyfile" \
    -out "$certfile" \
    -days 3650 \
    -config "$openssl_config" >/dev/null 2>&1
  rm -f "$openssl_config"
  run_root chmod 600 "$keyfile"
  run_root chmod 644 "$certfile"
}

ensure_hostname_resolution() {
  local current_hostname
  current_hostname="$(hostname 2>/dev/null || true)"
  [[ -n "$current_hostname" ]] || return
  if grep -qE "^[[:space:]]*127\\.0\\.1\\.1[[:space:]].*\\b${current_hostname}\\b" /etc/hosts 2>/dev/null; then
    return
  fi
  log "Adding hostname '$current_hostname' to /etc/hosts for sudo/systemd compatibility"
  printf '127.0.1.1 %s\n' "$current_hostname" | run_root tee -a /etc/hosts >/dev/null
}

install_systemd_service() {
  (( INSTALL_SERVICE )) || return
  command -v systemctl >/dev/null 2>&1 || return

  log "Installing systemd service at $SERVICE_FILE"
  local tmp_service
  tmp_service="$(mktemp /tmp/picarx-unified-service-XXXXXX)"
  cat > "$tmp_service" <<EOF
[Unit]
Description=PiCar-X Unified Control Stack
After=network-online.target sound.target avahi-daemon.service
Wants=network-online.target avahi-daemon.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$ENV_FILE
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=HOME=/root
Environment=USER=root
Environment=LOGNAME=root
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$PROJECT_DIR/src
# Allow write access to project and PiCar-X config directories
ProtectSystem=false
ProtectHome=false
ReadWritePaths=$PROJECT_DIR /opt/picar-x
# Add network capabilities for WiFi monitor mode and packet capture
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_SYS_RAWIO CAP_SYS_ADMIN
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_SYS_RAWIO CAP_SYS_ADMIN
# Allow all device access (needed for I2C, GPIO, camera, etc.)
DevicePolicy=auto
ExecStartPre=/bin/bash -c 'for i in {1..30}; do i2cdetect -y 1 | grep -q "14" && exit 0; sleep 2; done; i2cdetect -y 1 || true'
ExecStart=$VENV_DIR/bin/python -m picarx_unified
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  run_root cp "$tmp_service" "$SERVICE_FILE"
  rm -f "$tmp_service"
  run_root systemctl daemon-reload
  run_root systemctl enable "$SERVICE_NAME"
  # Create PiCar-X config directory if it doesn't exist
  run_root mkdir -p /opt/picar-x
  run_root chown -R root:root /opt/picar-x
  run_root chmod -R 777 /opt/picar-x
}

install_avahi_service() {
  command -v avahi-daemon >/dev/null 2>&1 || return
  local src="$PROJECT_DIR/deploy/picarx.avahi"
  [[ -f "$src" ]] || return
  log "Installing Avahi mDNS service advertisement"
  run_root mkdir -p /etc/avahi/services
  run_root cp "$src" /etc/avahi/services/picarx.service
  run_root chmod 644 /etc/avahi/services/picarx.service
  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl restart avahi-daemon || true
  fi
}

prepare_runtime_env() {
  ensure_env_file
  ensure_env_defaults
  load_env_file
  ensure_https_certificate

  export PICARX_HOST="${HOST_OVERRIDE:-${PICARX_HOST:-0.0.0.0}}"
  export PICARX_PORT="${PORT_OVERRIDE:-${PICARX_PORT:-8080}}"
  export PYTHONUNBUFFERED=1

  if (( MOCK_MODE )); then
    export PICARX_USE_MOCK=1
    export PICARX_FORCE_MOCK_CAMERA=1
  fi
}

run_application() {
  [[ -d "$VENV_DIR" ]] || fail "Virtual environment not found. Run this script without --run-only first."

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  prepare_runtime_env

  local scheme="http"
  case "${PICARX_HTTPS_ENABLE:-false}" in
    1|true|yes|on) scheme="https" ;;
  esac
  log "Starting PiCar-X Unified on ${scheme}://${PICARX_HOST}:${PICARX_PORT}"
  if (( MOCK_MODE )); then
    log "Mock mode is enabled"
  fi

  exec python -m picarx_unified
}

print_access_urls() {
  local scheme="http"
  case "${PICARX_HTTPS_ENABLE:-false}" in
    1|true|yes|on) scheme="https" ;;
  esac
  local port="${PICARX_PORT:-8080}"
  local hostname
  hostname="$(hostname 2>/dev/null || echo picarx)"
  local lan_ip
  lan_ip="$(python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || true)"

  printf '\n%s\n' "=========================================================="
  printf '%s\n'   " PiCar-X dashboard access URLs"
  printf '%s\n'   "=========================================================="
  if [[ -n "$lan_ip" ]]; then
    printf '  %s://%s:%s/\n' "$scheme" "$lan_ip" "$port"
    printf '    ^ use this IP if .local does not resolve in your browser\n'
  fi
  printf '  %s://%s.local:%s/\n' "$scheme" "$hostname" "$port"
  printf '%s\n\n' "=========================================================="
}

main() {
  if (( INSTALL_DEPS )); then
    install_system_packages
    install_sunfounder_stack
    ensure_virtualenv
    ensure_env_file
    ensure_env_defaults
    ensure_hostname_resolution
    install_samba_netbios
    install_systemd_service
    install_avahi_service
    prepare_runtime_env
  fi

  if (( RUN_APP )); then
    run_application
  elif (( START_SERVICE )); then
    command -v systemctl >/dev/null 2>&1 || fail "systemctl is required for --service"
    log "Starting $SERVICE_NAME"
    run_root systemctl restart "$SERVICE_NAME"
    run_root systemctl status "$SERVICE_NAME" --no-pager
    print_access_urls
  else
    log "Installation complete"
    printf 'Run the app later with:\n  bash scripts/install_pi.sh --run-only\n'
    if (( INSTALL_SERVICE )) && command -v systemctl >/dev/null 2>&1; then
      printf 'Or start the boot service with:\n  sudo systemctl start %s\n' "$SERVICE_NAME"
    fi
    print_access_urls
  fi
}

main "$@"
