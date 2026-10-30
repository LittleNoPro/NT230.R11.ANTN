#!/usr/bin/env bash
# End-to-end reproduction after scripts/fetch_sources.sh (or unpacking samples.zip).
set -euo pipefail
cd "$(dirname "$0")/../src"
python build_manifest.py
python run_extract.py --workers 8
python run_extract.py --missing --workers 8   # isolates the 2 files that segfault PHP-Parser
python prepare_graphs.py
python splits.py
python baselines.py
python experiments.py table2 ablation table4 clean cross sweep
python analyze.py
