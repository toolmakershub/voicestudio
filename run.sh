#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
export HF_HUB_OFFLINE=1
echo "Open http://127.0.0.1:7860 in your browser"
python -m uvicorn app:app --host 127.0.0.1 --port 7860
