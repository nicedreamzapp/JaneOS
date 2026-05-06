#!/bin/bash
# JaneOS — first-time setup
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[setup] creating .venv with python3.12"
  /opt/homebrew/bin/python3.12 -m venv .venv
fi

./.venv/bin/pip install --upgrade pip --quiet
./.venv/bin/pip install -r requirements.txt --quiet

mkdir -p data
echo "[setup] done. start with: ./launch.sh"
