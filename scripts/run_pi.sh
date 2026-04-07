#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_DIR/.venv/bin/activate"

export PICARX_HOST="${PICARX_HOST:-0.0.0.0}"
export PICARX_PORT="${PICARX_PORT:-8080}"

exec python -m picarx_unified
