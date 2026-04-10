#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE_FILE="$PROJECT_DIR/.env.example"

INSTALL_DEPS=1
RUN_APP=1
MOCK_MODE=0
SKIP_SUNFOUNDER=0
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
  5. Launches the app

Options:
  --install-only        Install everything but do not start the app
  --run-only            Skip installation and just run the app
  --mock                Run in mock hardware/camera mode
  --skip-sunfounder     Do not auto-install the official SunFounder stack
  --host HOST           Override PICARX_HOST for this run
  --port PORT           Override PICARX_PORT for this run
  --help                Show this message

Examples:
  bash scripts/install_pi.sh
  bash scripts/install_pi.sh --mock
  bash scripts/install_pi.sh --install-only
  bash scripts/install_pi.sh --run-only --host 0.0.0.0 --port 8080
EOF
}

while (($# > 0)); do
  case "$1" in
    --install-only)
      RUN_APP=0
      ;;
    --run-only)
      INSTALL_DEPS=0
      ;;
    --mock)
      MOCK_MODE=1
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

install_system_packages() {
  log "Installing Raspberry Pi OS packages"
  run_root apt update
  run_root apt install -y \
    git \
    python3 \
    python3-venv \
    python3-pip \
    python3-opencv \
    python3-picamera2 \
    espeak-ng \
    alsa-utils
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
}

ensure_virtualenv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment"
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  log "Installing Python package and dependencies"
  python -m pip install --upgrade pip setuptools wheel
  pip install -e "$PROJECT_DIR"
}

ensure_env_file() {
  if [[ -f "$ENV_FILE" ]] || [[ ! -f "$ENV_EXAMPLE_FILE" ]]; then
    return
  fi

  log "Creating .env from .env.example"
  cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
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

prepare_runtime_env() {
  ensure_env_file
  load_env_file

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

  log "Starting PiCar-X Unified on http://${PICARX_HOST}:${PICARX_PORT}"
  if (( MOCK_MODE )); then
    log "Mock mode is enabled"
  fi

  exec python -m picarx_unified
}

main() {
  if (( INSTALL_DEPS )); then
    install_system_packages
    install_sunfounder_stack
    ensure_virtualenv
    ensure_env_file
    prepare_runtime_env
  fi

  if (( RUN_APP )); then
    run_application
  else
    log "Installation complete"
    printf 'Run the app later with:\n  bash scripts/install_pi.sh --run-only\n'
  fi
}

main "$@"
