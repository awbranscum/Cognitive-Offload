#!/usr/bin/env sh
# Start Cognitive Offload on macOS/Linux.
cd "$(dirname "$0")" || exit 1
exec python3 main.py "$@"
