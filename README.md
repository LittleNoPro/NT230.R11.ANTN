# GlareShell reproduction (NT230)

Reproduction and critical re-evaluation of **GlareShell: Graph learning-based PHP webshell detection for web
server of industrial internet** (Feng et al., *Computer Networks* 245, 2024, doi:10.1016/j.comnet.2024.110406).
The original code and dataset are not public; everything here is rebuilt from the paper's description.

Report: [`report/main.tex`](report/main.tex) → `report/main.pdf`.

## ⚠️ Safety rules (read first)
* The corpus contains **real, working webshells**. They are only **parsed** (PHP-Parser) and read as bytes.
  No script in this repository includes, requires, evaluates or serves a sample. Never put `samples/` under a
  web server's document root, never run `php <sample>`.
* `samples/`, `data/processed/` (contains code fragments) and `tools/` are git-ignored. The repo ships only
  hashes, paths, scripts and aggregate numbers.
* To hand the corpus to a grader: `scripts/pack_samples.sh` → password-protected zip (`infected`) + SHA-256.
  Share it privately; never upload it publicly.
* Recommended: run inside the Docker image with `--network none` and the samples mounted read-only, or in a
  disposable VM snapshot (roll back after use). Antivirus software may quarantine files under `samples/`.

## Layout
```
scripts/   fetch_sources.sh  setup_tools.sh  reproduce.sh  pack_samples.sh
src/       build_manifest.py   provenance, hashes, 2-level dedup          -> data/manifests/manifest_all.csv
           php/extract_icfg.php LChecker CFGs + Algorithm 1 ICFG, pruning, normalisation, risk levels
           run_extract.py      parallel extraction                         -> data/processed/icfg/*.jsonl
           prepare_graphs.py   statement vocabularies + arrays             -> data/processed/graphs.pkl
           splits.py           near-dup clusters + 3 protocols x 5 seeds   -> data/splits/*.json
           embeddings.py       GloVe / W2V-c / W2V-s / D2V-m / D2V-w / FastText (trained on train split only)
           train_gnn.py        GCN / GIN / GAT + mean pooling + MLP (one run)
           experiments.py      all GNN runs (resumable)                    -> results/runs/*.json
           baselines.py        TF-IDF+LR/XGB, rules, graph-stats XGB
           analyze.py          tables, figures, error taxonomy            -> results/tables, report/figures
docs/      DATA_CARD.md  LABEL_GUIDE.md  SCHEMA.md
report/    LaTeX report
```

## Reproduce
Tested on WSL2 Ubuntu 24.04, PHP 8.3 CLI, Python 3.11, RTX 3050 6 GB, 7.6 GB RAM.
```bash
bash scripts/setup_tools.sh             # LChecker @c8a3646 + PHP-Parser v4.19.4 (no composer)
bash scripts/fetch_sources.sh           # clones all sources at pinned tags into samples/raw
unzip samples/raw/webshell/Cyc1e183__PHP-Webshell-Dataset/PHP-Webshell.zip \
      -d samples/raw/webshell/Cyc1e183__PHP-Webshell-Dataset/extracted
conda create -n glareshell python=3.11 && conda activate glareshell
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
bash scripts/reproduce.sh               # ~7 h on the machine above (GNN runs dominate)
cd report && pdflatex main && pdflatex main
```
Or with Docker (no network at run time):
```bash
docker build -t glareshell-repro .
docker run --rm --gpus all --network none -v "$PWD/samples:/work/samples:ro" \
  -v "$PWD/data:/work/data" -v "$PWD/results:/work/results" glareshell-repro bash scripts/reproduce.sh
```
Integrity: `sha256sum -c` against `data/manifests/manifest_all.csv` (column `sha256`) verifies every sample.

## Deviations from the paper (all discussed in the report)
| Paper | Here | Why |
|---|---|---|
| LChecker CFG + ICFG | LChecker's `ConstructCFG` reused verbatim; ICFG/Algorithm 1, pruning, normalisation, risk written by us | paper code not released |
| — | namespaces / try-catch / declare flattened; nested functions & closures hoisted; uncalled functions kept as components | vanilla LChecker drops them → most modern benign files become empty graphs |
| — | `short_open_tag=On` when parsing | 208 webshells use only `<?` tags and would otherwise parse as HTML |
| ICFG unbounded | capped at 2,000 statements | RAM (15% of webshells hit the cap) |
| ysrc/webshell-sample | only via the Cyc1e183 aggregate | repository deleted |
| GloVe "default" | own PyTorch GloVe (x_max=100, α=0.75, 25 epochs) | `glove-python` no longer installs |
| FastText bucket 2M | 200k | RAM |
| D2V PV-DBOW default | `dbow_words=1` | otherwise statement vectors are never trained |
| single run | 5 seeds, mean ± 95% t-CI | rubric / statistical validity |
