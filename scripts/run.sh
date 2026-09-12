#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ -f ".env" ]; then set -a; source .env 2>/dev/null; set +a; fi
pip install -q -r requirements.txt 2>&1 | tail -1
python3 main.py "$@"
