"""Near-duplicate clustering and the three evaluation protocols.

  paper_random : paper sources, exact-hash dedup, benign subsampled to the paper's 10,375,
                 stratified random 8:1:1 (the paper's protocol)                     -> reproduction
  clean_group  : same sources, whitespace-dedup + near-duplicate clusters never cross
                 train/val/test (group split 8:1:1)                                  -> leakage control
  cross_source : train/val of clean_group; test = held-out projects/collections that are
                 not near-duplicates of anything in the paper sources                -> generalisation

Near duplicates: Jaccard >= 0.8 between the sets of normalised ICFG statements (MinHash-LSH
candidate generation, exact Jaccard verification, union-find).
"""
import json
import pickle
from collections import defaultdict

import numpy as np
import pandas as pd

from common import DATA, PROC, SPLITS

N_BENIGN_PAPER = 10375
SEEDS = [0, 1, 2, 3, 4]
JACCARD = 0.8
N_PERM, BANDS = 128, 32
P = (1 << 61) - 1


def minhash(sets):
    rng = np.random.default_rng(12345)
    a = rng.integers(1, P, N_PERM, dtype=np.uint64)
    b = rng.integers(0, P, N_PERM, dtype=np.uint64)
    sig = np.full((len(sets), N_PERM), np.iinfo(np.uint64).max, dtype=np.uint64)
    for i, s in enumerate(sets):
        if s:
            x = np.fromiter(s, dtype=np.uint64)[:, None]
            sig[i] = ((a * x + b) % np.uint64(P)).min(0)
    return sig


def near_dup_clusters(keys, sets):
    parent = list(range(len(keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sig = minhash(sets)
    r = N_PERM // BANDS
    n_pairs = 0
    for band in range(BANDS):
        buckets = defaultdict(list)
        chunk = sig[:, band * r:(band + 1) * r]
        for i in range(len(keys)):
            if sets[i]:
                buckets[chunk[i].tobytes()].append(i)
        for idx in buckets.values():
            if len(idx) < 2 or len(idx) > 2000:   # giant buckets = trivial shared statements
                continue
            for j in idx[1:]:
                a, b = find(idx[0]), find(j)
                if a == b:
                    continue
                s1, s2 = sets[idx[0]], sets[j]
                if len(s1 & s2) / len(s1 | s2) >= JACCARD:
                    parent[b] = a
                    n_pairs += 1
    return np.array([find(i) for i in range(len(keys))]), n_pairs


def group_split(df, seed, frac=(0.8, 0.1, 0.1)):
    """Assign whole clusters to train/val/test, separately per label, to hit the target fractions."""
    rng = np.random.default_rng(seed)
    out = {}
    for lab, d in df.groupby("y"):
        cl = d.groupby("cluster").size()
        order = rng.permutation(cl.index.values)
        tot, acc = cl.sum(), 0
        for c in order:
            part = "train" if acc < frac[0] * tot else ("val" if acc < (frac[0] + frac[1]) * tot else "test")
            out[c] = out.get(c, part)
            acc += cl[c]
    return df.cluster.map(out)


def main():
    SPLITS.mkdir(parents=True, exist_ok=True)
    G = pickle.load(open(PROC / "graphs.pkl", "rb"))["graphs"]
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    man = man[man.keep_exact == 1].copy()
    man["y"] = (man.label == "webshell").astype(int)
    keys = man.sha256.tolist()
    sets = [frozenset(G[k]["norm"].tolist()) for k in keys]
    cl, n_pairs = near_dup_clusters(keys, sets)
    # empty graphs are only grouped by whitespace hash
    man["cluster"] = [f"c{c}" if s else f"w{h}" for c, s, h in zip(cl, sets, man.ws_hash)]
    ws_rep = man.groupby("ws_hash").cluster.transform("first")       # whitespace dups share a cluster
    man["cluster"] = ws_rep
    mixed = man.groupby("cluster").label.nunique()
    man["cluster_mixed"] = man.cluster.map(mixed > 1).astype(int)
    man[["sha256", "label", "subset", "source", "cluster", "cluster_mixed"]].to_csv(DATA / "manifests/clusters.csv", index=False)
    print("verified near-dup merges", n_pairs, "clusters", man.cluster.nunique(), "mixed-label clusters", int((mixed > 1).sum()))
    for (lab, sub), d in man.groupby(["label", "subset"]):
        print(f"  {lab:8s} {sub:8s} files={len(d):6d} clusters={d.cluster.nunique():6d}")

    paper = man[man.subset == "paper"]
    rng = np.random.default_rng(2024)
    ben = paper[paper.y == 0]
    # benign subsample to the paper's size, proportional per source
    take = (ben.groupby("source").size() * N_BENIGN_PAPER / len(ben)).round().astype(int)
    ben_sub = pd.concat([d.sample(min(len(d), take[s]), random_state=2024) for s, d in ben.groupby("source")])
    P_exact = pd.concat([paper[paper.y == 1], ben_sub])
    P_clean = P_exact[P_exact.keep_ws == 1]
    P_clean = P_clean[P_clean.cluster_mixed == 0]
    held = man[(man.subset == "heldout") & (man.keep_ws == 1)]
    paper_clusters = set(paper.cluster)
    held_novel = held[~held.cluster.isin(paper_clusters) & (held.cluster_mixed == 0)]
    print("paper_random", P_exact.y.value_counts().to_dict(), "clean", P_clean.y.value_counts().to_dict(),
          "heldout", held.y.value_counts().to_dict(), "heldout novel", held_novel.y.value_counts().to_dict())

    from sklearn.model_selection import train_test_split
    for seed in SEEDS:
        tr, rest = train_test_split(P_exact, test_size=0.2, stratify=P_exact.y, random_state=seed)
        va, te = train_test_split(rest, test_size=0.5, stratify=rest.y, random_state=seed)
        sp = {"train": tr.sha256.tolist(), "val": va.sha256.tolist(), "test": te.sha256.tolist()}
        json.dump(sp, open(SPLITS / f"paper_random_s{seed}.json", "w"))
        # leakage measure: test samples sharing a near-dup cluster with a training sample
        trc = set(tr.cluster)
        leak = te.assign(leak=te.cluster.isin(trc)).groupby("y").leak.mean().to_dict()

        part = group_split(P_clean, seed)
        sp2 = {k: P_clean.sha256[part == k].tolist() for k in ("train", "val", "test")}
        json.dump(sp2, open(SPLITS / f"clean_group_s{seed}.json", "w"))
        sp3 = {"train": sp2["train"], "val": sp2["val"], "test": held_novel.sha256.tolist()}
        json.dump(sp3, open(SPLITS / f"cross_source_s{seed}.json", "w"))
        print(f"seed {seed}: paper_random test leak rate (by label) {leak}; clean sizes",
              {k: len(v) for k, v in sp2.items()})


# leave-one-collection-out: webshells whose earliest public source is collection X form the test set
ORIGINS = {"tennc": "tennc__webshell", "bartblaze": "bartblaze__PHP-backdoors", "xl7dev": "xl7dev__WebShell"}


def origin_splits():
    """loo_<origin>_s<seed>: benign as in clean_group; test webshells = origin X; train/val webshells =
    all other clean webshells minus every near-duplicate cluster that contains a test file."""
    man = pd.read_csv(DATA / "manifests/manifest_all.csv", dtype={"first_seen": str})
    man = man[man.keep_exact == 1].drop_duplicates("sha256").set_index("sha256")
    cl = pd.read_csv(DATA / "manifests/clusters.csv").drop_duplicates("sha256").set_index("sha256").cluster
    for seed in SEEDS:
        cg = json.load(open(SPLITS / f"clean_group_s{seed}.json"))
        allk = cg["train"] + cg["val"] + cg["test"]
        lab = man.loc[allk, "label"]
        ws = lab.index[lab == "webshell"]
        ben = {k: [s for s in cg[k] if man.at[s, "label"] == "benign"] for k in ("train", "val", "test")}
        for short, origin in ORIGINS.items():
            test_ws = [s for s in ws if man.at[s, "origin"] == origin]
            bad = set(cl.loc[test_ws])
            rest = pd.DataFrame(dict(cluster=cl.loc[[s for s in ws if s not in set(test_ws)]]))
            rest = rest[~rest.cluster.isin(bad)]
            rng = np.random.default_rng(seed)
            cls = rng.permutation(rest.cluster.unique())
            val_cl = set(cls[: max(1, len(cls) // 9)])
            sp = {"train": ben["train"] + rest.index[~rest.cluster.isin(val_cl)].tolist(),
                  "val": ben["val"] + rest.index[rest.cluster.isin(val_cl)].tolist(),
                  "test": ben["test"] + test_ws}
            json.dump(sp, open(SPLITS / f"loo_{short}_s{seed}.json", "w"))
            if seed == 0:
                print(f"loo_{short}: test webshells {len(test_ws)}, test benign {len(ben['test'])}, "
                      f"train webshells {len(rest) - len(rest[rest.cluster.isin(val_cl)])}, "
                      f"dropped (same cluster as test) {len(ws) - len(test_ws) - len(rest)}")


if __name__ == "__main__":
    import sys
    origin_splits() if sys.argv[1:] == ["origin"] else main()
