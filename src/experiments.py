"""All GNN experiments. Resumable: a run whose results/runs/<name>.json exists is skipped.

  python experiments.py table2 table4 ablation sweep clean cross origin
"""
import gc
import sys
import traceback

import torch

from common import RUNS
from train_gnn import parse, run

SEEDS = [0, 1, 2, 3, 4]
METHODS = ["glove", "w2v_c", "w2v_s", "d2v_m", "d2v_w", "fasttext"]
# Table 2 / Fig. 6-8 setting (paper §4.3): GCN, 2 layers, hidden 10, batch 10
T2 = ["--gnn", "gcn", "--layers", "2", "--hidden", "10", "--batch", "10", "--epochs", "50", "--patience", "10"]
# Table 3 optimum (paper §4.4)
T3 = {"gcn": ["--hidden", "32"], "gat": ["--hidden", "8", "--heads", "8"], "gin": ["--hidden", "16"]}
T3_COMMON = ["--layers", "3", "--batch", "256", "--lr", "0.001", "--epochs", "120", "--patience", "30"]


def jobs(group):
    if group == "table2":
        for m in METHODS:
            for s in SEEDS:
                yield f"t2_{m}_s{s}", ["--emb", m, "--seed", str(s)] + T2
    if group == "ablation":
        for v in ("none", "n"):
            for s in SEEDS:
                yield f"abl_{v}_s{s}", ["--emb", "fasttext", "--variant", v, "--seed", str(s)] + T2
    if group == "table4":
        for g in ("gcn", "gin", "gat"):
            for s in SEEDS:
                yield f"t4_{g}_s{s}", ["--emb", "fasttext", "--gnn", g, "--seed", str(s)] + T3[g] + T3_COMMON
    if group == "sweep":
        for d in (20, 40, 60, 80, 120):
            for s in SEEDS[:3]:
                yield f"dim{d}_s{s}", ["--emb", "fasttext", "--dim", str(d), "--seed", str(s)] + T2
        for w in (2, 3, 4, 6, 7):
            for s in SEEDS[:3]:
                yield f"win{w}_s{s}", ["--emb", "fasttext", "--window", str(w), "--seed", str(s)] + T2
    if group == "clean":
        for g in ("gcn", "gat"):
            for s in SEEDS:
                yield f"clean_{g}_s{s}", ["--split", "clean_group", "--emb", "fasttext", "--gnn", g,
                                          "--seed", str(s)] + T3[g] + T3_COMMON
        for v in ("none", "n"):
            for s in SEEDS:
                yield f"clean_abl_{v}_s{s}", ["--split", "clean_group", "--emb", "fasttext", "--gnn", "gat",
                                              "--variant", v, "--seed", str(s)] + T3["gat"] + T3_COMMON
    if group == "cross":
        for g in ("gcn", "gat"):
            for s in SEEDS:
                yield f"cross_{g}_s{s}", ["--split", "cross_source", "--emb_split", "clean_group", "--emb", "fasttext",
                                          "--gnn", g, "--seed", str(s)] + T3[g] + T3_COMMON
    if group == "origin":
        for o in ("tennc", "bartblaze", "xl7dev"):
            for g in ("gcn", "gat"):
                for s in SEEDS:
                    yield f"loo_{o}_{g}_s{s}", ["--split", f"loo_{o}", "--emb", "fasttext", "--gnn", g,
                                                "--seed", str(s)] + T3[g] + T3_COMMON
    if group == "hard":  # improvement experiment, run alone: GLARESHELL_GRAPHS=graphs_aug.pkl
        for kind in ("base", "aug"):
            for s in SEEDS:
                yield f"hard_{kind}_gat_s{s}", ["--split", kind, "--emb", "fasttext", "--gnn", "gat",
                                                "--seed", str(s)] + T3["gat"] + T3_COMMON


def main(groups):
    if "hard" in groups:
        import os
        assert groups == ["hard"] and os.environ.get("GLARESHELL_GRAPHS") == "graphs_aug.pkl", \
            "run as: GLARESHELL_GRAPHS=graphs_aug.pkl python experiments.py hard"
    for grp in groups:
        for name, args in jobs(grp):
            if (RUNS / f"{name}.json").exists():
                continue
            try:
                r = run(parse(["--name", name] + args))
                t = r["test"]
                print(f"{name:22s} F1={t['f1']:.4f} P={t['precision']:.4f} R={t['recall']:.4f} "
                      f"FPR={t['fpr']:.4f} ep={r['epochs_run']} t={r['secs_train']:.0f}s", flush=True)
            except Exception:
                traceback.print_exc()
            gc.collect()
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main(sys.argv[1:])
