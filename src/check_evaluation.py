"""Validate a corrected v2 evaluation and seal its evidence (standard library only).

Usage: python src/check_evaluation.py --run-root reproductions/v2 [--inputs-only]
Unlike check_artifacts.py, this command never interprets the legacy v1 clusters as v2.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SEEDS = range(5)
BASELINES = ("tfidf_lr", "tfidf_xgb", "struct_xgb", "rule_crit", "rule_risk", "rule_risk_input")
MAIN_SPLITS = ("paper_random", "clean_group", "cross_source", "loo_tennc", "loo_bartblaze", "loo_xl7dev")


def read_json(path):
    return json.loads(path.read_text())


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def expected_runs():
    """Independent inventory of the published experimental plan, including configurations."""
    expected = {}

    def gnn(name, seed, split="paper_random", t3=False, **changes):
        cfg = dict(name=name, seed=seed, split=split, emb="fasttext", dim=100, window=5,
                   variant="nw", gnn="gcn", layers=2, hidden=10, heads=8, batch=10,
                   lr=.001, epochs=50, patience=10)
        cfg.update(changes)
        if t3:
            cfg.update(layers=3, batch=256, epochs=120, patience=30)
            cfg["hidden"] = {"gcn": 32, "gin": 16, "gat": 8}[cfg["gnn"]]
        expected[name] = cfg

    for split in MAIN_SPLITS:
        for seed in SEEDS:
            for model in BASELINES:
                name = f"bl_{split}_{model}_s{seed}"
                expected[name] = dict(name=name, model=model, split=split, seed=seed)
    for seed in SEEDS:
        for emb in ("glove", "w2v_c", "w2v_s", "d2v_m", "d2v_w", "fasttext"):
            gnn(f"t2_{emb}_s{seed}", seed, emb=emb)
        for model in ("gcn", "gat", "gin"):
            gnn(f"t4_{model}_s{seed}", seed, t3=True, gnn=model)
        for variant in ("none", "n"):
            gnn(f"abl_{variant}_s{seed}", seed, variant=variant)
            gnn(f"clean_abl_{variant}_s{seed}", seed, "clean_group", t3=True, gnn="gat", variant=variant)
        for model in ("gcn", "gat"):
            gnn(f"clean_{model}_s{seed}", seed, "clean_group", t3=True, gnn=model)
            gnn(f"cross_{model}_s{seed}", seed, "cross_source", t3=True, gnn=model, emb_split="clean_group")
            for origin in ("tennc", "bartblaze", "xl7dev"):
                gnn(f"loo_{origin}_{model}_s{seed}", seed, f"loo_{origin}", t3=True, gnn=model)
        for kind in ("base", "aug"):
            gnn(f"hard_{kind}_gat_s{seed}", seed, kind, t3=True, gnn="gat")
            name = f"bl_{kind}_tfidf_lr_s{seed}"
            expected[name] = dict(name=name, split=kind, seed=seed)
    for seed in range(3):
        for dim in (20, 40, 60, 80, 120):
            gnn(f"dim{dim}_s{seed}", seed, dim=dim)
        for window in (2, 3, 4, 6, 7):
            gnn(f"win{window}_s{seed}", seed, window=window)
    gnn("final_demo_gat", 0, "clean_group", t3=True, gnn="gat")
    return expected


def check_prediction(result, split, labels, where):
    pred = result["pred"]
    if set(pred) != {"sha", "y", "p"} or len({len(pred[k]) for k in pred}) != 1:
        raise ValueError(f"{where}: inconsistent prediction arrays")
    if pred["sha"] != split["test"]:
        raise ValueError(f"{where}: predictions differ from ordered test IDs")
    counts = Counter()
    for sha, y, probability in zip(pred["sha"], pred["y"], pred["p"]):
        if y != int(labels[sha] == "webshell") or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError(f"{where}: invalid label/probability for {sha}")
        counts[("tp" if y else "fp") if probability >= .5 else ("fn" if y else "tn")] += 1
    if any(counts[k] != result["test"][k] for k in ("tp", "tn", "fp", "fn")):
        raise ValueError(f"{where}: confusion matrix differs from saved predictions")
    tp, tn, fp, fn = (counts[k] for k in ("tp", "tn", "fp", "fn"))
    div = lambda a, b: a / b if b else float("nan")
    p, r = div(tp, tp + fp), div(tp, tp + fn)
    f1 = 2 * p * r / (p + r) if math.isfinite(p) and math.isfinite(r) and p + r else 0.
    expected = dict(precision=p, recall=r, tnr=div(tn, tn + fp), fpr=div(fp, tn + fp),
                    acc=div(tp + tn, tp + tn + fp + fn), f1=f1)
    for metric, value in expected.items():
        actual = result["test"][metric]
        if not ((math.isnan(value) and math.isnan(actual)) or math.isclose(value, actual, abs_tol=1e-9)):
            raise ValueError(f"{where}: metric mismatch for {metric}")


def validate(run_root, inputs_only=False):
    run_root = Path(run_root).resolve()
    data, results = run_root / "data", run_root / "results"
    if read_json(data / "manifests/hash_protocol.json")["version"] != "php-token-whitespace-v2":
        raise ValueError("v2 token hash protocol is required")
    if read_json(data / "splits/protocol.json")["clustering"] != "minhash-all-pairs-v2":
        raise ValueError("v2 clustering protocol is required")
    main_rows = [r for r in read_csv(data / "manifests/manifest_all.csv") if r["keep_exact"] == "1"]
    main = {r["sha256"]: r for r in main_rows}
    if len(main) != len(main_rows):
        raise ValueError("duplicate kept SHA-256 IDs in main manifest")
    hard_path = data / "manifests/manifest_hard.csv"
    hard = {r["sha256"]: r for r in read_csv(hard_path)} if hard_path.exists() else {}
    if main.keys() & hard.keys():
        raise ValueError("hard-benign IDs overlap the main corpus")
    if {r["ws_hash"] for r in main.values()} & {r["ws_hash"] for r in hard.values()}:
        raise ValueError("hard-benign token hashes overlap the main corpus")
    samples = main | hard
    labels = {sha: r["label"] for sha, r in samples.items()}
    clusters = {r["sha256"]: r["cluster"] for r in read_csv(data / "manifests/clusters.csv")}
    graph_stats = {r["sha256"]: r for r in read_csv(data / "processed/graph_stats.csv")}
    if set(graph_stats) != set(main) or set(clusters) != set(main):
        raise ValueError("main graph statistics, cluster IDs and kept manifest IDs differ")
    split_names = [f"{name}_s{seed}" for name in MAIN_SPLITS for seed in SEEDS]
    if not inputs_only:
        split_names += [f"{name}_s{seed}" for name in ("base", "aug") for seed in SEEDS]
    splits, split_summary = {}, {}
    for name in split_names:
        split = read_json(data / f"splits/{name}.json")
        for part in ("train", "val", "test"):
            ids = split[part]
            if not ids or len(ids) != len(set(ids)) or set(ids) - samples.keys():
                raise ValueError(f"{name}/{part}: empty, repeated or unknown IDs")
            if set(labels[sha] for sha in ids) != {"benign", "webshell"}:
                raise ValueError(f"{name}/{part}: both classes required")
        for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
            if set(split[a]) & set(split[b]):
                raise ValueError(f"{name}: sample overlap between {a} and {b}")
            if not name.startswith("paper_random"):
                ca, cb = [{clusters[x] for x in split[k] if x in clusters} for k in (a, b)]
                if ca & cb:
                    raise ValueError(f"{name}: recorded main-corpus cluster overlap between {a} and {b}")
        if name.startswith("cross_source"):
            train_sources = {main[x]["source"] for x in split["train"] + split["val"]}
            if train_sources & {main[x]["source"] for x in split["test"]}:
                raise ValueError(f"{name}: project/collection overlap with test sources")
        splits[name] = split
        split_summary[name] = {k: dict(Counter(labels[s] for s in v)) for k, v in split.items()}
    if not inputs_only:
        for seed in SEEDS:
            base, aug = (splits[f"{k}_s{seed}"] for k in ("base", "aug"))
            if base["test"] != aug["test"]:
                raise ValueError("base and augmented experiments must share ordered test IDs")
            if base["train"] != splits[f"clean_group_s{seed}"]["train"] or base["val"] != splits[f"clean_group_s{seed}"]["val"]:
                raise ValueError("base experiment differs from clean training/validation sets")
            for k in ("train", "val"):
                added = set(aug[k]) - set(base[k])
                if set(base[k]) - set(aug[k]) or any(hard[s]["subset"] != "hard_train" for s in added):
                    raise ValueError(f"augmented {k} contains unexpected samples")
        expected = expected_runs()
        paths = {p.stem: p for p in (results / "runs").glob("*.json")}
        if paths.keys() != expected.keys():
            raise ValueError(f"run inventory mismatch: missing={sorted(expected.keys() - paths.keys())}, "
                             f"unexpected={sorted(paths.keys() - expected.keys())}")
        for name, cfg in expected.items():
            result = read_json(paths[name])
            if result["cfg"] != cfg:
                raise ValueError(f"{name}: unexpected configuration: {result['cfg']}")
            split = splits[f"{cfg['split']}_s{cfg['seed']}"]
            check_prediction(result, split, labels, name)
            if "gnn" in cfg:
                if result.get("runtime", {}).get("device") != "cuda":
                    raise ValueError(f"{name}: missing evidence that this run used CUDA")
                if result["n"] != {k: len(v) for k, v in split.items()}:
                    raise ValueError(f"{name}: dataset size mismatch")
                if not 1 <= result["epochs_run"] <= cfg["epochs"]:
                    raise ValueError(f"{name}: invalid epoch count")
        for file in ("summary.json", "probe_benign.txt", "probe_tfidf.json"):
            if not (results / file).is_file():
                raise ValueError(f"missing final analysis/probe output: {file}")
        for file in ("gat.pt", "fasttext.kv"):
            if not (run_root / "models" / file).is_file():
                raise ValueError(f"missing demonstration model: {file}")
    output = dict(status="passed", stage="main inputs" if inputs_only else "complete evaluation",
                  checked_at_utc=datetime.now(timezone.utc).isoformat(), checked_splits=len(splits),
                  checked_runs=0 if inputs_only else len(expected_runs()), main_samples=len(main),
                  hard_benign_samples=len(hard), split_counts=split_summary,
                  limitations=["MinHash-LSH is approximate; cluster disjointness does not prove exhaustive deduplication",
                               "The hard-benign extension removes exact/token duplicates; its added files are not near-duplicate clustered",
                               "Source collection labels are not independent human verification",
                               "Cross-source projects remain static public-corpus tests, not industrial server deployment tests"])
    results.mkdir(parents=True, exist_ok=True)
    (results / ("input_check.json" if inputs_only else "evaluation_check.json")).write_text(json.dumps(output, indent=2) + "\n")
    if not inputs_only:
        files = []
        for directory in (data / "manifests", data / "splits", results / "runs", results / "tables", results / "figures"):
            files += [p for p in directory.rglob("*") if p.is_file()]
        files += [data / "processed/graph_stats.csv", data / "processed/graph_stats_hard.csv",
                  results / "evaluation_check.json", results / "summary.json", run_root / "environment.json",
                  results / "probe_benign.txt", results / "probe_tfidf.json"]
        seal = {p.relative_to(run_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
        provenance = dict(protocol="v2-evidence-sha256", sha256=seal)
        (results / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--inputs-only", action="store_true")
    parser.add_argument("--verify-seal", action="store_true", help="verify the existing evidence hashes without replacing them")
    args = parser.parse_args()
    if args.verify_seal:
        root = args.run_root.resolve()
        seal = read_json(root / "results/provenance.json")
        for relative, expected_hash in seal["sha256"].items():
            path = root / relative
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"invalid provenance path: {relative}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"evidence checksum mismatch: {relative}")
        print(f"Verified {len(seal['sha256'])} sealed v2 artifacts")
        raise SystemExit(0)
    result = validate(args.run_root, args.inputs_only)
    print(json.dumps({k: v for k, v in result.items() if k != "split_counts"}, indent=2))
