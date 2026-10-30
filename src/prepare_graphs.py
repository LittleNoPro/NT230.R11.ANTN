"""Convert extractor JSONL into compact arrays.

data/processed/graphs.pkl:
  vocab_norm / vocab_raw : list[str]  statement vocabularies (normalised / raw text)
  graphs : dict sha256 -> dict(norm=int32[n], raw=int32[n], risk=int8[n], edges=int32[2,E], meta...)
data/processed/graph_stats.csv : per-sample extraction statistics (safe to publish, no code)
"""
import json
import pickle

import numpy as np
import pandas as pd

from common import PROC, DATA


def main():
    vocab = {"norm": {}, "raw": {}}
    graphs, stats = {}, []

    def vid(kind, s):
        d = vocab[kind]
        if s not in d:
            d[s] = len(d)
        return d[s]

    for part in sorted((PROC / "icfg").glob("part-*.jsonl")):
        for line in open(part):
            r = json.loads(line)
            nodes = r.get("nodes", []) if r.get("ok") else []
            e = np.asarray(r.get("edges", []), dtype=np.int32).reshape(-1, 2).T
            g = dict(norm=np.asarray([vid("norm", n[0]) for n in nodes], np.int32),
                     raw=np.asarray([vid("raw", n[1]) for n in nodes], np.int32),
                     risk=np.asarray([n[2] for n in nodes], np.int8),
                     edges=np.ascontiguousarray(e))
            graphs[r["id"]] = g
            stats.append(dict(sha256=r["id"], ok=int(bool(r.get("ok"))), err=r.get("err", ""),
                              parse_error=int(bool(r.get("parse_error"))), truncated=int(bool(r.get("truncated"))),
                              n_nodes=len(nodes), n_edges=e.shape[1], n_pruned=r.get("n_pruned", 0),
                              n_funcs=r.get("n_funcs", 0), n_crit=int((g["risk"] == 2).sum()),
                              n_obf=int((g["risk"] == 1).sum()), secs=r.get("secs", 0)))
    # samples whose extractor process crashed (PHP segfault) have no record: keep them as failures
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    empty_e = np.zeros((2, 0), np.int32)
    for sha in man.loc[man.keep_exact == 1, "sha256"]:
        if sha not in graphs:
            graphs[sha] = dict(norm=np.zeros(0, np.int32), raw=np.zeros(0, np.int32), risk=np.zeros(0, np.int8), edges=empty_e)
            stats.append(dict(sha256=sha, ok=0, err="crash", parse_error=0, truncated=0, n_nodes=0, n_edges=0,
                              n_pruned=0, n_funcs=0, n_crit=0, n_obf=0, secs=0))
    out = dict(vocab_norm=list(vocab["norm"]), vocab_raw=list(vocab["raw"]), graphs=graphs)
    with open(PROC / "graphs.pkl", "wb") as f:
        pickle.dump(out, f, protocol=5)
    st = pd.DataFrame(stats)
    st = st.merge(man[["sha256", "label", "subset", "source"]].drop_duplicates("sha256"), on="sha256", how="left")
    st.to_csv(PROC / "graph_stats.csv", index=False)
    print("graphs", len(graphs), "vocab_norm", len(vocab["norm"]), "vocab_raw", len(vocab["raw"]))
    print(st.groupby(["label", "subset"]).agg(n=("sha256", "size"), fail=("ok", lambda s: (s == 0).sum()),
                                              parse_err=("parse_error", "sum"), empty=("n_nodes", lambda s: (s == 0).sum()),
                                              trunc=("truncated", "sum"), med_nodes=("n_nodes", "median"),
                                              secs=("secs", "mean")))


if __name__ == "__main__":
    main()
