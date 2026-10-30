# Schemas

## data/manifests/manifest_all.csv (one row per candidate file)
| column | type | meaning |
|---|---|---|
| sha256 | hex | SHA-256 of file bytes (sample id everywhere) |
| md5 | hex | MD5 (used to recover provenance inside the Cyc1e183 aggregate, which names files by MD5) |
| ws_hash | hex | SHA-256 of the bytes with all whitespace removed |
| label | `webshell`/`benign` | source-level label (docs/LABEL_GUIDE.md) |
| subset | `paper`/`heldout` | paper Table 1 source vs. extension source |
| source | str | `owner__repo` |
| origin | str | for Cyc1e183 files: the individual collection matched by MD5, else `unknown`; otherwise = source |
| relpath | str | path inside the source checkout |
| size | int | bytes |
| is_php | 0/1 | contains `<?` |
| first_seen | date | first commit adding the file (only for full-history webshell clones) |
| dup_of | hex16 | representative's sha256 prefix if this file is a whitespace duplicate |
| label_conflict | 0/1 | duplicates carry both labels |
| keep_exact | 0/1 | representative after exact-hash dedup (paper protocol) |
| keep_ws | 0/1 | representative after whitespace-insensitive dedup |
| prio | int | source priority used to choose representatives |

## data/manifests/clusters.csv
`sha256, label, subset, source, cluster, cluster_mixed` — near-duplicate cluster id (Jaccard ≥ 0.8 between the
sets of normalised ICFG statements; whitespace duplicates always share a cluster); `cluster_mixed` = cluster
contains both labels.

## data/splits/<protocol>_s<seed>.json
`{"train": [sha256], "val": [sha256], "test": [sha256]}` for protocol ∈ {paper_random, clean_group, cross_source}, seed ∈ 0..4.

## data/processed/icfg/part-*.jsonl (git-ignored: contains code fragments)
One JSON per file: `id`, `ok`, `err`, `parse_error`, `truncated`, `n_pruned`, `n_funcs`, `secs`,
`nodes: [[normalised_stmt, raw_stmt, risk]]` (risk 0 normal / 1 obfuscated / 2 critical), `edges: [[src, dst]]`.

## data/processed/graph_stats.csv, graph_feats.csv (safe: numbers only)
Per-file extraction statistics and the 12 graph statistics used by the `struct_xgb` baseline.

## results/runs/<run>.json
`cfg` (all hyper-parameters, seed, split), `test` (tp, tn, fp, fn, precision, recall, tnr, fpr, acc, f1),
`val_f1`, `history` (epoch, loss, val F1), timings, `pred` (sha, y, p) for error analysis.
