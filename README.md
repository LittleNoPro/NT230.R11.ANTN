# GlareShell reproduction — NT230

A reconstruction and critical evaluation of **GlareShell: Graph learning-based PHP webshell detection for web
server of industrial internet**, Feng et al., *Computer Networks* 245 (2024),
[DOI 10.1016/j.comnet.2024.110406](https://doi.org/10.1016/j.comnet.2024.110406).

The project provides the PHP parser/graph builder, pinned corpus, controlled splits, GNN/text/rule baselines,
retained predictions, uncertainty/error analysis, and an original 22-file benign construct artifact.
The authors' implementation and exact corpus were unavailable for this reconstruction.

<!-- EVALUATION_STATUS -->
The corrected v2 evaluation is complete: **346 runs and 40 splits passed validation**, with 416 sealed artifacts. All 13 regression tests passed in the measured GPU image. Both PDFs passed build/layout checks (main 6 pages; extended 15 pages; presentation 12 slides). All report pages and slides passed rendered-image review; concept-map overlap and slide-table flow were corrected. The independent human label audit remains pending and is disclosed.
<!-- /EVALUATION_STATUS -->

Reports: [main PDF](report/main.pdf), [extended PDF](report/extended.pdf), [12-slide presentation](report/slides.pdf).
Documentation: [data card](docs/DATA_CARD.md), [label guide](docs/LABEL_GUIDE.md),
[schemas](docs/SCHEMA.md), [construct study](docs/CONSTRUCT_CASES.md).

<!-- V2_RESULTS -->
## Measured v2 results

Five seeds, mean ± 95% seed interval unless shown as means. These are static corpus results.

| Measurement | Corrected v2 result |
|---|---|
| GCN / GIN / GAT random F1 | 0.979 / 0.981 / 0.980 |
| GAT clean F1 | 0.965 ± 0.009 |
| TF-IDF+LR clean F1 | 0.992 ± 0.007 |
| Random test webshells sharing a training component | 76.9% ± 5.8% |
| GAT FPR on unseen benign projects | 1.40% ± 0.68% |
| GAT recall on 20 novel source-labelled webshells | 0.630 ± 0.034 |
| GAT / LR recall at 0.1% test-ROC FPR budget | 0.140 / 0.690 (oracle thresholds) |
| GAT benign-probe flags | 10 / 12 |
| Matched extra-benign training: GAT pooled FPR | 2.51% → 1.09% |
| Matched extra-benign training: all-webshell recall | 0.932 → 0.910 |
| Matched extra-benign training: novel-webshell recall | 0.640 → 0.480 |
| Original construct artifact | 22 benign fixtures, 11 pairs, CC0; no detection-accuracy claim |
<!-- /V2_RESULTS -->

## Evidence versions and limits

- Root data/ and results/ retain **historical v1** inputs and predictions. Their 390 sealed hashes verify
  346 saved runs and 40 splits. V1 used an over-aggressive byte whitespace hash and incomplete LSH comparisons.
  Its protocol status is itself historical sealed evidence.
- Corrected checked evidence belongs under **evaluation/v2/**. Full private intermediates and weights are under
  reproductions/v2/. Never pair new splits with old predictions.
- V2 lexical hashes preserve strings/comments; all eligible LSH bucket pairs and lexical equivalences share one
  union-find. LSH remains approximate. Auxiliary benign files have exact/token deduplication, without the main
  track's near-duplicate clustering.
- Labels are source-level proxies. The original 150 blinded audit copies are restored, but **all 300 independent
  human decisions remain pending**. No agreement or label-error prevalence is claimed.
- Test-ROC alarm budgets are optimistic oracle bounds. Seed intervals and collection holdouts do not establish
  future-family or industrial-server effectiveness. No malware is executed or deployed.

## Project layout

| Path | Purpose |
|---|---|
| sources.lock.tsv | Full commits, history mode and license references for 24 sources |
| src/php/ | Static PHP graph extraction and lexical hashing |
| src/build_manifest.py, clustering.py, splits.py | Provenance, duplicate control and evaluation partitions |
| src/embeddings.py, train_gnn.py, experiments.py | Six embeddings, three GNNs, ablations/sweeps/holdouts |
| src/baselines.py, hard_benign.py | Lexical/rule/statistics baselines and matched benign-application experiment |
| src/check_evaluation.py, run_metadata.py | Complete v2 validation and evaluated runtime/source fingerprints |
| report/render_metrics.py | Generate manuscript values/tables from a verified snapshot |
| tests/construct_cases/, results/construct_cases/ | Original CC0 fixtures and exact graph observations |
| data/, results/ | Historical v1 metadata and saved predictions |
| evaluation/v2/ | Complete checked v2 manifests, splits, predictions, analyses and runtime |
| samples/, tools/, reproductions/v2/ | Private fetched code, tools, graphs, caches and weights; Git-ignored |

## Verify evidence without a GPU

Standard-library Python is sufficient for hash/prediction checks.

    python3 src/check_artifacts.py
    python3 src/check_evaluation.py --run-root evaluation/v2 --verify-seal

Full validation of a private run also
checks the demonstration-model files:

    python3 src/check_evaluation.py --run-root reproductions/v2

The validator checks exact run names/configurations, test IDs and labels, full-precision probabilities,
recomputed confusion matrices/metrics, main-corpus cluster separation, cross-source project separation and
matched base/aug test membership. Its scope limitations are retained in evaluation_check.json.

## Rebuild the reports

After the v2 evidence check passes, generate values and build both PDFs:

    python3 report/render_metrics.py --evidence evaluation/v2
    bash scripts/build_report.sh

This requires TeX Live with IEEEtran/BibTeX and Poppler. Metric/table generation uses standard-library Python;
it requires neither raw samples nor a GPU. The build checks unresolved warnings, captions before references,
page bounds and balanced final main-report columns. Visual review complements these checks.

To recompute analyses from saved predictions, use Python 3.11 with the pinned NumPy/pandas/SciPy/matplotlib/
scikit-learn versions from requirements.txt. Generate into a working copy to preserve published checksums:

    mkdir -p reproductions/analysis-review
    cp -a evaluation/v2/data evaluation/v2/results reproductions/analysis-review/
    GLARESHELL_DATA="$PWD/reproductions/analysis-review/data" \
      GLARESHELL_RESULTS="$PWD/reproductions/analysis-review/results" \
      python src/analyze.py --saved-only

Saved-only analysis preserves extraction/error/timing sections from the retained summary; rebuilding those sections
requires the raw extraction files. The controlled fixtures can be regenerated with PHP CLI and the pinned tools:

    bash scripts/setup_tools.sh
    python3 src/construct_cases.py

## Full corrected reproduction

The measured GPU protocol uses Python 3.11, PHP 8.2.35, PyTorch 2.4.1+cu121, PyG 2.6.1 and Gensim 4.3.3.
The existing Dockerfile installs the training environment and pinned parser/CFG tools.
Host fetching needs Python >=3.11 and Git; it never executes a PHP sample.

    bash scripts/fetch_sources.sh --workers 4
    bash scripts/fetch_sources.sh --verify-only --workers 4
    docker build -t glareshell-repro .

Check a real CUDA computation before starting:

    docker run --rm --gpus all --network none glareshell-repro python -c \
      'import torch; assert torch.cuda.is_available(); x=torch.ones((32,32),device="cuda"); print(torch.cuda.get_device_name(0),(x@x).sum().item())'

Then run with samples read-only and an isolated output root:

    mkdir -p reproductions
    GLARESHELL_IMAGE_ID="$(docker image inspect glareshell-repro --format '{{.Id}}')"
    docker run -d --name glareshell-v2 --gpus all --network none \
      --user "$(id -u):$(id -g)" --cpus 8 --memory 8g --memory-swap 8g \
      -e PYTHONHASHSEED=0 -e GIT_OPTIONAL_LOCKS=0 \
      -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=1 \
      -e GLARESHELL_EXTRACT_WORKERS=4 -e GLARESHELL_IMAGE_ID="$GLARESHELL_IMAGE_ID" \
      -v "$PWD/samples:/work/samples:ro" \
      -v "$PWD/reproductions:/work/reproductions" \
      glareshell-repro bash scripts/reproduce.sh
    docker logs -f glareshell-v2

This canonical sequence runs the same configurations sequentially. The measured VPS execution overlaps
independent groups, with its actual resource limits recorded in environment.json. The full suite can take hours;
FastText statement embedding is CPU work even when GNNs use CUDA. Analysis, verification and report rendering do
not require a GPU. The end-to-end GPU recipe deliberately rejects a silent CPU fallback.

The source fetcher reuses completed downloads, verifies exact commits and materializes the aggregate LFS object.
It refuses mismatched/modified tracked checkouts. New output goes to reproductions/v2/{data,results,models}.
GLARESHELL_RUN_ROOT selects another absolute output root.

Resume only with identical code, runtime, source bytes and input files; use a fresh root after an input/method
change. Completed GNN files are skipped by name. The baseline/demo stages can recompute work. The environment
fingerprint prevents silently mixing incompatible resumptions. Raw code/ICFG fragments and embedding caches
are not submission files.

## Demo and private data

After training, retain the complete models directory including Gensim sidecars. With Python/PHP/tools available:

    GLARESHELL_MODELS="$PWD/reproductions/v2/models" \
      python src/detect.py tests/probe_benign

The detector parses input and prints scores/risk statements. It never executes or includes the target PHP.
Listed risky statements are capability indicators, not a causal explanation or proof of malicious intent.
The handwritten probes and PHP-Construct-22 are stress/representation studies, not representative deployment-FPR samples.

The copied trained checkpoint also passed a CPU-only portability check on all 12 probes: verdicts, statement
counts and printed probabilities match the VPS output. See [demo validation](results/demo_validation.json).
This checks model portability, not detection accuracy on a representative population.

The training image can run the same demo without GPU access:

    docker run --rm --network none -e GLARESHELL_MODELS=/models \
      -v "$PWD/reproductions/v2/models:/models:ro" \
      glareshell-repro python src/detect.py tests/probe_benign

For private grading handover, with zip installed:

    GLARESHELL_DATA="$PWD/evaluation/v2/data" \
      GLARESHELL_SAMPLE_ARCHIVE=samples/glareshell_v2_private.zip \
      bash scripts/pack_samples.sh

The archive uses password infected and has a SHA-256 checksum. Keep raw samples and archives private.
It contains retained main/auxiliary files; rebuilding candidate/Git provenance still uses the full pinned fetch.
The data card describes licenses, labels, splits and limits.

## Important deviations and interpretation choices

| Paper description | Reconstruction choice |
|---|---|
| LChecker CFG plus ICFG | Reuse pinned CFG code; implement call/return linking, pruning, normalisation and risk in a wrapper |
| PHP representation | Flatten namespace/declare/exception wrappers; bound same-file call resolution; keep uncalled functions |
| Short tags / failure handling | Parse with short_open_tag=On; retain failed files as empty graphs |
| Graph/text size | Cap at 2,000 nodes and bounded statement/string text |
| Embedding input | One emitted statement is one word; each file's emission order is one sentence; training files only |
| FastText / Doc2Vec | 200k n-gram buckets; PV-DBOW uses dbow_words=1 |
| GloVe defaults | Recorded PyTorch implementation, 25 AdaGrad epochs |
| GNN fitting | Validation-F1 early stopping, fixed threshold 0.5, recorded widths/layers/batches |
| Evaluation | Five main seeds, three sweep seeds, source/cluster controls and matched baselines |
| Deployment scope | Offline static corpora only; no industrial-server deployment or runtime taint claim |

The reports distinguish reconstructed results, added experiments and claims not established by the evidence.
Independent human label review remains separate and pending; see AUDIT_PROTOCOL.md.
