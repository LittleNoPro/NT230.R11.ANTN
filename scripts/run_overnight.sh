#!/usr/bin/env bash
# Launch in the currently activated Python 3.11 training environment.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${GLARESHELL_RUN_ROOT:-$ROOT/reproductions/v2}"
mkdir -p "$RUN_ROOT"
nohup bash "$ROOT/scripts/reproduce.sh" > "$RUN_ROOT/run.log" 2>&1 &
echo "Started PID $!; log: $RUN_ROOT/run.log"
