#!/usr/bin/env bash
# End-to-end reproduction after scripts/fetch_sources.sh (or unpacking samples.zip).
set -euo pipefail
cd "$(dirname "$0")/../src"
python build_manifest.py
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
python probe.py                               # TF-IDF side of the benign probe
