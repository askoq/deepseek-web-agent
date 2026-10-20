#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "Error: Python 3.10+ is required but not found in PATH." >&2
    exit 1
fi

exec $PY bridge.py "$@"
