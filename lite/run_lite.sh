#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First-time setup: creating environment and installing Piper..."
  python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python app.py
