#!/usr/bin/env bash
# Set up and start novel2img on macOS / Linux:
#   creates .venv, installs the package (again whenever pyproject.toml changes),
#   creates .env from .env.example, then starts the web UI.
# Extra arguments go to the server, e.g. ./run.sh --port 9000
# Use another interpreter with PYTHON=python3.12 ./run.sh
set -eo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV_PYTHON=.venv/bin/python
STAMP=.venv/.novel2img-installed

if [ ! -x "$VENV_PYTHON" ]; then
  if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    echo "novel2img needs Python 3.9 or newer; '$PYTHON' is $("$PYTHON" --version 2>&1)." >&2
    echo "Point PYTHON at a newer interpreter, e.g. PYTHON=python3.12 ./run.sh" >&2
    exit 1
  fi
  echo "[setup] Creating virtual environment in .venv"
  "$PYTHON" -m venv .venv
fi

if ! cmp -s pyproject.toml "$STAMP"; then
  echo "[setup] Installing dependencies (the first run takes a while)"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e .
  cp pyproject.toml "$STAMP"
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[setup] Created .env from .env.example. Check SD_MODEL_PATH before generating."
fi

exec "$VENV_PYTHON" -m novel2img "$@"
