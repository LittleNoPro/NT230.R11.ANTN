# Schemas

Paths below are relative to an evidence root. Historical v1 uses the repository root; the corrected public v2
snapshot uses `evaluation/v2/`. Full private run files live in `reproductions/v2/`. Never join a v1 split to v2
predictions or infer protocol version from a filename alone.

## data/manifests/manifest_all.csv (one row per candidate file)
| column | type | meaning |
|---|---|---|
| sha256 | hex | SHA-256 of file bytes (sample id everywhere) |
| md5 | hex | MD5 (used to recover provenance inside the Cyc1e183 aggregate, which names files by MD5) |
| ws_hash | hex | v1: SHA-256 after deleting all byte whitespace; v2: SHA-256 of framed PHP lexical tokens excluding T_WHITESPACE, preserving string/comment bytes; see manifests/hash_protocol.json |
| label | `webshell`/`benign` | source-level label (docs/LABEL_GUIDE.md) |
| subset | `paper`/`heldout` | paper Table 1 source vs. extension source |
| source | str | `owner__repo` |
| origin | str | for Cyc1e183 files: the individual collection matched by MD5, else `unknown`; otherwise = source |
| relpath | str | path relative to the source/extraction directory; Cyc1e183 does not include another `extracted/` prefix |
| size | int | bytes |
| is_php | 0/1 | contains `<?` |
| first_seen | date | first commit adding the file (only for full-history webshell clones) |
| dup_of | hex16 | representative's sha256 prefix if this file is a whitespace duplicate |
| label_conflict | 0/1 | duplicates carry both labels |
| keep_exact | 0/1 | representative after exact-hash dedup (paper protocol) |
| keep_ws | 0/1 | representative after whitespace-insensitive dedup |
| prio | int | source priority used to choose representatives |

## data/manifests/clusters.csv
`sha256, label, subset, source, cluster, cluster_mixed` — connected-component ID from verified Jaccard ≥ 0.8 pairs of normalised-statement sets plus lexical-hash equivalence; transitivity does not require every pair in a component to reach 0.8; `cluster_mixed` = cluster
contains both labels.

## data/splits/<protocol>_s<seed>.json
`{"train": [sha256], "val": [sha256], "test": [sha256]}` for protocol ∈ {paper_random, clean_group, cross_source, loo_tennc, loo_bartblaze, loo_xl7dev, base, aug}, seed ∈ 0..4.

`data/splits/protocol.json` identifies legacy v1 or corrected v2 clustering. `results/provenance.json` seals
historical input and prediction hashes. The v2 run directory is separate: no new split may be paired with old
predictions. `sources.lock.tsv` contains directory, repository, full commit, history mode and license reference.

## Controlled construct artifact

`tests/construct_cases/manifest.json`: source, CC0 license, limitations, cases with id/file/pair/label/label_basis/split,
and pair interpretations. `results/construct_cases/<id>.json`: extractor fields plus source SHA-256 and explicit
classifier status. `summary.json` records tool revisions, extractor hash and observed pair comparisons.

## data/processed/icfg/part-*.jsonl (git-ignored: contains code fragments)
One JSON per file: `id`, `ok`, `err`, `parse_error`, `truncated`, `n_pruned`, `n_funcs`, `secs`,
`nodes: [[normalised_stmt, raw_stmt, risk]]` (risk 0 normal / 1 obfuscated / 2 critical), `edges: [[src, dst]]`.

## data/processed/graph_stats.csv, graph_feats.csv (safe: numbers only)
Per-file extraction statistics and the 12 graph statistics used by the `struct_xgb` baseline.

## results/runs/<run>.json
`cfg` (all hyper-parameters, seed, split), `test` (tp, tn, fp, fn, precision, recall, tnr, fpr, acc, f1),
GNN-only fields: `val_f1`, `history` (epoch, loss, validation F1), timings, `n` (partition counts),
and `runtime` (device, PyTorch/CUDA version, GPU). All runs contain `pred` with ordered `sha`, binary `y`
and full-precision `p`. Threshold 0.5 is applied before serialisation and independently recomputed by the v2
validator. Model probabilities are not human label judgments.

## environment.json and results/provenance.json (v2)

`environment.json` records the actual Python/PHP/PyTorch/CUDA/GPU, PHP extensions, installed package versions,
Docker image ID and SHA-256 of evaluated code/configuration/fixture files. It does not dump ambient credentials
or environment variables. `results/evaluation_check.json` records the completed inventory, split checks and
scope limitations. `results/provenance.json` maps evidence-root-relative paths to SHA-256 for the manifests,
splits, predictions, analysis tables/figures, numeric graph statistics and runtime record.

`python src/check_evaluation.py --run-root evaluation/v2 --verify-seal` verifies that published evidence
has not changed. Full recomputation of the validation additionally needs the local demonstration model files;
report generation and hash verification do not require those model files or a GPU.

## data/manifests/manifest_hard.csv

The auxiliary benign-application track adds `subset` ∈ {hard_train, hard_test, probe}, `revision`,
`source`, `relpath`, exact SHA-256 and the same v2 lexical hash. Its paired base/aug tests match IDs within each
seed. Added files are exact/token deduplicated, but are not covered by main-corpus near-duplicate clustering;
that narrower leakage control is an explicit limitation. `data/processed/graph_stats_hard.csv` gives numeric
extraction statistics for emitted auxiliary records; missing extractor records use empty graph fallbacks.
