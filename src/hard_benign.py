"""Improvement experiment: add small, procedural benign PHP applications ("hard benign") to training.

The main corpus (manifest_all.csv, graphs.pkl, existing splits) is left untouched; this track has its own
manifest, ICFG directory and an append-only extension of the vocabulary, so all earlier results stay valid.

  python hard_benign.py manifest   # samples/raw/benign_small -> data/manifests/manifest_hard.csv
  python hard_benign.py extract    # -> data/processed/icfg_hard/*.jsonl
  python hard_benign.py graphs     # graphs.pkl + hard files -> data/processed/graphs_aug.pkl
  python hard_benign.py splits     # base_s* / aug_s*: same test set, train without / with hard-train projects
  python hard_benign.py tfidf      # TF-IDF + LR on base and aug (GNNs: python experiments.py hard)

Test set (identical for base and aug): clean_group test + cross_source test + hard-test projects + the 12
hand-written probe scripts. Static only: files are parsed, never executed.
"""
import hashlib
import json
import pickle
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from common import DATA, PROC, RESULTS, ROOT, RUNS, SPLITS, dump_json, metrics

RAW = ROOT / "samples" / "raw" / "benign_small"
MAN = DATA / "manifests" / "manifest_hard.csv"
ICFG = PROC / "icfg_hard"
PHP_EXT = re.compile(r"\.(php[3-7]?|phtml|inc)$", re.I)
TRAIN_PROJECTS = ["YOURLS__YOURLS", "fluxbb__fluxbb", "splitbrain__dokuwiki", "Cacti__cacti", "vrana__adminer"]
TEST_PROJECTS = ["opnsense__core", "osTicket__osTicket", "mybb__mybb", "prasathmani__tinyfilemanager"]
CAP = 1000  # max files per training project, so no single project dominates


def ws_hash(b):
    return hashlib.sha256(re.sub(rb"\s+", b"", b)).hexdigest()


def manifest():
    old = pd.read_csv(DATA / "manifests/manifest_all.csv", usecols=["sha256", "ws_hash"])
    seen_ws = set(old.ws_hash)
    rows = []
    projects = [(p, RAW / p, "hard_train" if p in TRAIN_PROJECTS else "hard_test") for p in TRAIN_PROJECTS + TEST_PROJECTS]
    projects.append(("probe_benign", ROOT / "tests/probe_benign", "probe"))
    for name, d, subset in projects:
        rev = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() \
            if (d / ".git").exists() else ""
        for f in sorted(d.rglob("*")):
            if not f.is_file() or ".git" in f.parts or not PHP_EXT.search(f.name):
                continue
            b = f.read_bytes()
            if b"<?" not in b:
                continue
            rows.append(dict(sha256=hashlib.sha256(b).hexdigest(), ws_hash=ws_hash(b), label="benign", subset=subset,
                             source=name, relpath=str(f.relative_to(d)), size=len(b), revision=rev, path=str(f)))
    m = pd.DataFrame(rows)
    n0 = len(m)
    m = m[~m.ws_hash.isin(seen_ws)].drop_duplicates("ws_hash")  # no overlap with the main corpus or within this track
    parts = []
    for (sub, src), d in m.groupby(["subset", "source"]):
        parts.append(d.sample(min(len(d), CAP), random_state=2024) if sub == "hard_train" else d)
    m = pd.concat(parts).sort_values(["subset", "source", "relpath"])
    MAN.parent.mkdir(parents=True, exist_ok=True)
    m.drop(columns="path").to_csv(MAN, index=False)
    m[["sha256", "path"]].to_csv(PROC / "hard_paths.tsv", sep="\t", index=False, header=False)
    print(f"{n0} candidate files -> {len(m)} after dedup/cap")
    print(m.groupby(["subset", "source"]).size().to_string())


def extract():
    ICFG.mkdir(parents=True, exist_ok=True)
    rows = [l.rstrip("\n") for l in open(PROC / "hard_paths.tsv")]
    chunks = [rows[i:i + 150] for i in range(0, len(rows), 150)]

    def run(i, chunk):
        out = ICFG / f"part-{i:04d}.jsonl"
        if out.exists():
            return 0
        lst = ICFG / f"part-{i:04d}.tsv"
        lst.write_text("\n".join(chunk) + "\n")
        tmp = out.with_suffix(".tmp")
        p = subprocess.run(["php", "-d", "short_open_tag=On", str(ROOT / "src/php/extract_icfg.php"), str(lst), str(tmp)],
                           capture_output=True, timeout=1800)
        tmp.rename(out)
        lst.unlink()
        return p.returncode

    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda t: run(*t), enumerate(chunks)))
    done = {json.loads(l)["id"] for p in ICFG.glob("part-*.jsonl") for l in open(p)}
    print("chunks", len(chunks), "non-zero exit", sum(c != 0 for c in codes), "records", len(done), "of", len(rows))


def graphs():
    with open(PROC / "graphs.pkl", "rb") as f:
        G = pickle.load(f)
    voc = {k: {s: i for i, s in enumerate(G[f"vocab_{k}"])} for k in ("norm", "raw")}
    n0 = len(voc["norm"])

    def vid(kind, s):  # append-only: existing statement ids are unchanged
        d = voc[kind]
        if s not in d:
            d[s] = len(d)
        return d[s]

    m = pd.read_csv(MAN)
    empty = dict(norm=np.zeros(0, np.int32), raw=np.zeros(0, np.int32), risk=np.zeros(0, np.int8),
                 edges=np.zeros((2, 0), np.int32))
    stats = []
    for part in sorted(ICFG.glob("part-*.jsonl")):
        for line in open(part):
            r = json.loads(line)
            nodes = r.get("nodes", []) if r.get("ok") else []
            e = np.asarray(r.get("edges", []), dtype=np.int32).reshape(-1, 2).T
            G["graphs"][r["id"]] = dict(norm=np.asarray([vid("norm", n[0]) for n in nodes], np.int32),
                                        raw=np.asarray([vid("raw", n[1]) for n in nodes], np.int32),
                                        risk=np.asarray([n[2] for n in nodes], np.int8), edges=np.ascontiguousarray(e))
            stats.append(dict(sha256=r["id"], n_nodes=len(nodes), parse_error=int(bool(r.get("parse_error")))))
    for s in m.sha256:  # extractor crash -> empty graph, as in the main corpus
        G["graphs"].setdefault(s, empty)
    G["vocab_norm"], G["vocab_raw"] = list(voc["norm"]), list(voc["raw"])
    with open(PROC / "graphs_aug.pkl", "wb") as f:
        pickle.dump(G, f, protocol=5)
    st = pd.DataFrame(stats).merge(m[["sha256", "subset", "source"]], on="sha256")
    print("new statements", len(voc["norm"]) - n0)
    print(st.groupby(["subset", "source"]).agg(n=("sha256", "size"), empty=("n_nodes", lambda s: int((s == 0).sum())),
                                               median_nodes=("n_nodes", "median")).to_string())


def splits():
    m = pd.read_csv(MAN)
    tr_hard = m[m.subset == "hard_train"]
    te_hard = m[m.subset != "hard_train"].sha256.tolist()
    for seed in range(5):
        cg = json.load(open(SPLITS / f"clean_group_s{seed}.json"))
        xs = json.load(open(SPLITS / f"cross_source_s{seed}.json"))
        test = cg["test"] + xs["test"] + te_hard
        rng = np.random.default_rng(seed)
        va_mask = rng.random(len(tr_hard)) < 0.1
        json.dump({"train": cg["train"], "val": cg["val"], "test": test}, open(SPLITS / f"base_s{seed}.json", "w"))
        json.dump({"train": cg["train"] + tr_hard.sha256[~va_mask].tolist(),
                   "val": cg["val"] + tr_hard.sha256[va_mask].tolist(), "test": test},
                  open(SPLITS / f"aug_s{seed}.json", "w"))
    print("test files", len(test), "hard-train added", len(tr_hard))


def texts(keys):
    from baselines import file_text
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    man = man[man.keep_exact == 1].drop_duplicates("sha256").set_index("sha256")
    paths = dict(l.rstrip("\n").split("\t") for l in open(PROC / "hard_paths.tsv"))
    return [Path(paths[k]).read_bytes()[:100_000].decode("latin-1") if k in paths else file_text(man.loc[k]) for k in keys]


def tfidf():
    from scipy.sparse import vstack as sp_vstack
    from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
    from sklearn.linear_model import LogisticRegression
    from baselines import TOKEN
    lab = pd.read_csv(DATA / "manifests/manifest_all.csv", usecols=["sha256", "label"]).drop_duplicates("sha256")
    ymap = dict(zip(lab.sha256, (lab.label == "webshell").astype(int)))
    hv = HashingVectorizer(token_pattern=TOKEN, lowercase=False, ngram_range=(1, 2), n_features=1 << 18,
                           alternate_sign=False, norm=None, dtype=np.float32)
    cache = {}

    def X(keys):
        miss = [k for k in keys if k not in cache]
        for i in range(0, len(miss), 500):
            for k, row in zip(miss[i:i + 500], hv.transform(texts(miss[i:i + 500]))):
                cache[k] = row
        return sp_vstack([cache[k] for k in keys]).tocsr()

    for seed in range(5):
        for kind in ("base", "aug"):
            name = f"bl_{kind}_tfidf_lr_s{seed}"
            if (RUNS / f"{name}.json").exists():
                continue
            sp = json.load(open(SPLITS / f"{kind}_s{seed}.json"))
            y = np.array([ymap.get(k, 0) for k in sp["train"]])
            tf = TfidfTransformer(sublinear_tf=True)
            lr = LogisticRegression(C=10, max_iter=3000).fit(tf.fit_transform(X(sp["train"])), y)
            p = lr.predict_proba(tf.transform(X(sp["test"])))[:, 1]
            yt = [ymap.get(k, 0) for k in sp["test"]]
            t = metrics(yt, p >= 0.5)
            dump_json(dict(cfg=dict(name=name, split=kind, seed=seed), test=t,
                           pred=dict(sha=sp["test"], y=yt, p=[round(float(x), 5) for x in p])), RUNS / f"{name}.json")
            print(f"{name:24s} FPR={t['fpr']:.4f} R={t['recall']:.4f}", flush=True)


if __name__ == "__main__":
    {"manifest": manifest, "extract": extract, "graphs": graphs, "splits": splits, "tfidf": tfidf}[sys.argv[1]]()
