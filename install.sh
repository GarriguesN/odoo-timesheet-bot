#!/usr/bin/env bash
# Thin wrapper — la logica esta en install.py (multiplataforma)
set -euo pipefail
"$(dirname "$0")/.venv/bin/python3" "$(dirname "$0")/install.py" 2>/dev/null || \
python3 "$(dirname "$0")/install.py"
