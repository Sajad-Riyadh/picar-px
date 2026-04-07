#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  python3-opencv \
  python3-picamera2 \
  espeak-ng \
  alsa-utils

if ! python3 - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("picarx") else 1)
PY
then
  echo
  echo "The official SunFounder PiCar-X library is not installed."
  echo "Install the official stack first:"
  echo "  https://docs.sunfounder.com/projects/picar-x-v20/en/latest/python/python_start/install_all_modules.html"
  echo
  echo "The official repository install command is:"
  echo "  git clone -b v2.0 https://github.com/SunFounder/picar-x.git /tmp/picar-x"
  echo "  cd /tmp/picar-x && sudo python3 setup.py install"
  echo
fi

python3 -m venv "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"
python -m pip install --upgrade pip
pip install -e "$PROJECT_DIR"

echo
echo "Installation complete."
echo "Activate the environment with:"
echo "  source \"$PROJECT_DIR/.venv/bin/activate\""
