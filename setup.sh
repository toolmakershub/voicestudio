#!/usr/bin/env bash
# One-time setup (needs internet) for macOS / Linux.
set -e
cd "$(dirname "$0")"
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python download_model.py
echo "Setup complete. Run ./run.sh to start the studio."
