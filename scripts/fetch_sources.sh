#!/usr/bin/env bash
# Fetch locked revisions and unpack the PHP aggregate; input files are never executed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/src/fetch_sources.py" "$@"
