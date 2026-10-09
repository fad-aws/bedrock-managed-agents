#!/usr/bin/env bash
#
# One-time (or as-needed) environment setup for Module 1 (environment=none).
#
# 1. Creates a Python virtual environment at ./.venv (safe to re-run; the
#    existing venv is reused if present).
# 2. Installs/upgrades the dependencies from requirements.txt into it
#    (openai[bedrock] + boto3). This step needs network access to PyPI.
#
# Run this once before starting the labs, and again whenever requirements.txt
# changes. After it finishes, activate the venv and run a lab script directly:
#
#   source .venv/bin/activate
#   python labs/lab-01-create-session/create_session.py "Hello, BMA!"
#
# Usage:
#   ./setup.sh
#
# Environment overrides:
#   VENV_DIR   venv location (default: ./.venv)
#   PYTHON     base interpreter used to create the venv (default: python3)
#   FORCE=1    delete and recreate the venv from scratch

set -euo pipefail

# Resolve the directory this script lives in, so it works from any cwd.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

VENV_DIR="${VENV_DIR:-"$SCRIPT_DIR/.venv"}"
PYTHON="${PYTHON:-python3}"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

if [ "${FORCE:-0}" = "1" ] && [ -d "$VENV_DIR" ]; then
  echo "FORCE=1: removing existing virtual environment at $VENV_DIR" >&2
  rm -rf "$VENV_DIR"
fi

# 1. Create the venv if it does not already exist.
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR" >&2
  "$PYTHON" -m venv "$VENV_DIR"
else
  echo "Reusing existing virtual environment at $VENV_DIR" >&2
fi

VENV_PY="$VENV_DIR/bin/python"

# 2. Install/upgrade dependencies.
echo "Installing dependencies from $REQUIREMENTS" >&2
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install --upgrade -r "$REQUIREMENTS"

cat >&2 <<'EOF'

Setup complete.

Next:
  1. Activate the virtual environment:
       source .venv/bin/activate
  2. Run a lab script, for example:
       python labs/lab-01-create-session/create_session.py "Hello, BMA!"

Each lab has its own README.md explaining what to run and what to expect.
EOF
