#!/usr/bin/env bash
# End-to-end reproduction after scripts/fetch_sources.sh; outputs are isolated from historical v1 artifacts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${GLARESHELL_RUN_ROOT:-$ROOT/reproductions/v2}"
export GLARESHELL_DATA="$RUN_ROOT/data"
export GLARESHELL_RESULTS="$RUN_ROOT/results"
export GLARESHELL_MODELS="$RUN_ROOT/models"
mkdir -p "$GLARESHELL_DATA" "$GLARESHELL_RESULTS"
python3 "$ROOT/src/fetch_sources.py" --verify-only
cd "$ROOT/src"
python build_manifest.py
bash "$ROOT/scripts/verify_checksums.sh"
python run_extract.py --workers 8
python run_extract.py --missing --workers 8   # isolates the 2 files that segfault PHP-Parser
python prepare_graphs.py
python splits.py
python splits.py origin                       # leave-one-collection-out splits
python baselines.py
python baselines.py loo_tennc loo_bartblaze loo_xl7dev
python experiments.py table2 ablation table4 clean cross sweep origin
python analyze.py
python train_final.py                         # demo model -> models/ (used by detect.py)
python detect.py "$ROOT/tests/probe_benign" > "$GLARESHELL_RESULTS/probe_benign.txt"
python probe.py                               # TF-IDF side of the benign probe
# improvement experiment: add small benign applications to training (separate track, main corpus untouched)
for step in manifest extract graphs splits; do python hard_benign.py $step; done
GLARESHELL_GRAPHS=graphs_aug.pkl python experiments.py hard
python hard_benign.py tfidf
python analyze.py
