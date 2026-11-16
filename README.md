# GlareShell reproduction (NT230)

Reproduction and critical re-evaluation of **GlareShell: Graph learning-based PHP webshell detection for web
server of industrial internet** (Feng et al., *Computer Networks* 245, 2024, doi:10.1016/j.comnet.2024.110406).
The original code and dataset are not public; everything here is rebuilt from the paper's description.

Report: [`report/main.tex`](report/main.tex) → `report/main.pdf`.

## Key results (5 seeds, mean ± 95% CI; paper: `report/main.pdf` (updated report), all tables: `report/extended.pdf`)
| | Paper | Ours |
|---|---|---|
| Best embedding (Table 2, GCN) | FastText 0.945 | FastText 0.977 ± 0.009 |
| GCN / GIN / GAT F1 (Table 4) | 0.968 / 0.977 / **0.989** | 0.981 / 0.983 / 0.980 (no significant difference detected) |
| TF-IDF + LR baseline F1 | — | **0.997** |
| Test webshells with a near-duplicate in train (random split) | — | 77% |
| GAT F1, cluster-disjoint split | — | 0.963 ± 0.008 |
| GAT FPR, 4 unseen benign projects | — | 1.7% (0.4% in-distribution) |
| Benign standalone scripts flagged (`tests/probe_benign`) | — | 10 / 12 |
| GAT recall at 0.1% FPR, unseen projects (TF-IDF + LR) | — | 0.06 (0.64) |
| GAT recall, leave-one-collection-out (TF-IDF + LR) | — | 0.92–0.95 (0.97–1.00) |
| Improvement: + 5 small benign apps in training → GAT FPR on all benign test files | — | 2.5% → 0.9% (p = 0.006), overall recall difference inconclusive; novel-set recall 0.644 → 0.544 |

A similar headline F1 is obtained on a rebuilt corpus; the component claims (best GNN, dimension curve, normalisation/risk ablation) are not
statistically supported (paired t / McNemar tests), and the benchmark is largely separable by code population rather than behaviour.

## Evidence status after review

All classifier numbers above are **historical version 1** results on the committed splits. Their exact inputs and
predictions are sealed in `results/provenance.json`; `python3 src/check_artifacts.py` verifies 346 runs and 40 splits.
The v1 near-duplicate algorithm missed some candidate comparisons, and its whitespace hash removed spaces inside
strings. Consequently the 77% figure is overlap in the recorded clusters, not exhaustive leakage measurement.
Version 2 fixes these issues and the benign-subsampling rounding error. **V2 classifier training has not been run**;
new output is isolated in `reproductions/v2/` and must not be mixed with the historical predictions.

The corrected hard-benign aggregation uses each run's own seed: GAT unseen-project FPR is **1.54% → 0.67%**,
and recall on the 18 novel webshells is **0.644 → 0.544** (paired p=0.22; inconclusive on this small set).
Overall FPR remains **2.52% → 0.92%** (p=0.006). Thresholds for recall at FPR 0.1% are chosen on the test set,
so those values are optimistic oracle bounds, not calibrated deployment performance.

A new **22-file benign construct artifact** (11 controlled pairs, CC0, analysis-only) includes source hashes,
exact graph JSON/DOT and a report section. It exposes loss of data dependencies, exception paths and arrow-function
handling; it carries no invented model verdicts. See `docs/CONSTRUCT_CASES.md`.

The three independent reviewers' 300 decisions for 150 selected corpus files are **pending**. No human agreement
or label-error prevalence is claimed. See `docs/AUDIT_PROTOCOL.md`.

Validation completed in the isolated analysis container: **8 regression tests passed**, 346 saved runs and
40 splits passed integrity checks (390 sealed input/prediction hashes), and all 22 construct graphs were generated.
Both PDFs were rebuilt with LaTeX/BibTeX: **7 pages** for the main report and **15 pages** for the extended version,
with no unresolved references or content overflow warnings.
The PDF build also checks rendered caption order and text bounds, and balances the main report's final columns.
Figures and tables are flushed before the bibliography so they cannot interrupt the reference list.
Final-page previews were also inspected visually. Local verification summaries are generated when the checks run.

Two empirical tasks remain: restore the v1 audit copies and obtain the three independent reviewers' decisions
as described in `docs/AUDIT_PROTOCOL.md`; then run the full v2 reproduction when the corpus and training environment
are available. Until those tasks finish, retain the historical model results and the explicit pending-audit status.

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
scripts/   fetch_sources.sh  setup_tools.sh  reproduce.sh  run_overnight.sh  pack_samples.sh  verify_checksums.sh
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
           train_final.py / detect.py  demo model + standalone detector / directory watcher
           probe.py            TF-IDF baseline on tests/probe_benign (shortcut probe)
docs/      DATA_CARD.md  LABEL_GUIDE.md  SCHEMA.md  AUDIT_PROTOCOL.md (manual label audit)
report/    LaTeX report
```

## Regenerate analyses and PDFs from saved predictions

This path needs no raw corpus, PyTorch or GPU. Use Python 3.11, PHP CLI, Git, TeX Live
(including `pdflatex`, `bibtex`, the extra LaTeX packages and recommended fonts), and Poppler (`pdftotext`).
```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install numpy==1.26.4 scipy==1.13.1 pandas==2.2.3 \
  matplotlib==3.9.2 scikit-learn==1.5.2
bash scripts/setup_tools.sh
python src/check_artifacts.py
python src/analyze.py --saved-only
python src/construct_cases.py
python -m unittest discover -s tests -p 'test_*.py' -v
bash scripts/build_report.sh
```
`--saved-only` preserves extraction/error/timing sections from the existing summary: recomputing those sections
requires the original extraction files. Construct fixtures are parsed only. All tables in the updated report are
regenerated from saved predictions or the construct runner; BibTeX is included in the PDF build.

## Full version 2 reproduction

The historical classifier environment was WSL2, PHP 8.3, Python 3.11 and RTX 3050 6 GB. The Docker recipe uses
PHP 8.2; record its precise runtime because built-in recognition can vary between PHP versions/extensions.
Fetch requires network access; the analysis/training run itself can use `--network none`.
```bash
bash scripts/setup_tools.sh
bash scripts/fetch_sources.sh  # 24 exact commits from sources.lock.tsv; also extracts the aggregate zip
# In a Python 3.11 environment:
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
bash scripts/reproduce.sh      # isolated data/results/models under reproductions/v2; training can take hours
```
Or:
```bash
docker build -t glareshell-repro .
docker run --rm --gpus all --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/samples:/work/samples:ro" -v "$PWD/reproductions:/work/reproductions" \
  glareshell-repro bash scripts/reproduce.sh
```
Create `reproductions/` before mounting it. For CPU-only training omit `--gpus all`.
`GLARESHELL_RUN_ROOT=/absolute/path` selects another isolated output directory.
The fetcher refuses mismatched/modified checkouts. It records full revisions and never retries at HEAD.
Integrity against the historical corpus, when available: `bash scripts/verify_checksums.sh`.
The reproduction script also verifies the newly built manifest before graph extraction.

## Demo (standalone detector)
```bash
cd src
python train_final.py                       # FastText + GAT on the leakage-controlled split -> models/
python detect.py path/to/file.php some/dir  # one-shot scan: verdict, probability, risky statements
python detect.py --watch ../tests/probe_benign   # re-scan new/modified .php files (paper's file monitor)
```
For a v2 model, first export `GLARESHELL_MODELS="$PWD/reproductions/v2/models"` from the repository root.
Model loading takes ~45 s (gensim rebuilds FastText word vectors); scoring a file takes milliseconds.
The detector only parses files; it never executes them.

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
