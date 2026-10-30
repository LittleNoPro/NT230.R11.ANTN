#!/usr/bin/env bash
# Resume all GNN experiments (finished runs in results/runs are skipped), then rebuild tables/figures.
# Runs detached with nohup so closing the terminal does not stop it. Log: results/logs/overnight.log
cd "$(dirname "$0")/.." || exit 1
source ~/miniforge3/etc/profile.d/conda.sh && conda activate glareshell
cd src
nohup bash -c 'python -u experiments.py table2 ablation table4 clean cross sweep 2>&1 | grep --line-buffered -v Warning; python analyze.py; echo ALL_DONE' \
  >> ../results/logs/overnight.log 2>&1 &
echo "started (pid $!). Progress: ls results/runs | grep -vc ^bl_   (target ~110)"
