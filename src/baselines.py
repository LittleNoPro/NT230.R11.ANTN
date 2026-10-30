"""Non-GNN baselines on the same splits.

  tfidf_lr / tfidf_xgb : TF-IDF over lexical PHP tokens of the raw file (1-2 grams)
  rule_crit            : webshell iff the ICFG has a critical statement (system/exec/...)
  rule_risk            : webshell iff it has a critical or obfuscated statement
  rule_risk_input      : rule_risk AND the file reads request input ($_GET/$_POST/...)
  struct_xgb           : XGBoost on 10 graph statistics only (no code semantics) — shortcut probe
Static only: files are read as bytes, nothing is executed.
"""
import json
import re
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.sparse import vstack as sp_vstack
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.linear_model import LogisticRegression

from common import DATA, PROC, ROOT, RUNS, SPLITS, dump_json, metrics

RAW = ROOT / "samples" / "raw"
TOKEN = r"\$?[A-Za-z_][A-Za-z0-9_]*|[^\sA-Za-z0-9_]"
INPUT = re.compile(r"\$_(GET|POST|REQUEST|COOKIE|FILES|SERVER)|php://input|getallheaders")


def file_text(r):
    base = RAW / "webshell" / "Cyc1e183__PHP-Webshell-Dataset" / "extracted" if r.source.startswith("Cyc1e183") \
        else RAW / r.label / r.source
    return (base / r.relpath).read_bytes()[:100_000].decode("latin-1")


def build_graph_feats():
    """Stream the extractor output once -> data/processed/graph_feats.csv (10 graph statistics per file)."""
    out = PROC / "graph_feats.csv"
    if out.exists():
        return pd.read_csv(out).set_index("sha256")
    rows = []
    for part in sorted((PROC / "icfg").glob("part-*.jsonl")):
        for line in open(part):
            r = json.loads(line)
            nodes = r.get("nodes", []) if r.get("ok") else []
            n, e = len(nodes), len(r.get("edges", [])) if r.get("ok") else 0
            risk = [x[2] for x in nodes]
            crit, obf = risk.count(2), risk.count(1)
            uniq = len({x[0] for x in nodes})
            rows.append(dict(sha256=r["id"], n_nodes=n, n_edges=e, density=e / max(n, 1), n_crit=crit, n_obf=obf,
                             frac_crit=crit / max(n, 1), frac_obf=obf / max(n, 1), uniq_stmt=uniq,
                             uniq_frac=uniq / max(n, 1), uses_input=int(any(INPUT.search(x[1]) for x in nodes)),
                             parse_error=int(bool(r.get("parse_error"))), truncated=int(bool(r.get("truncated")))))
    df = pd.DataFrame(rows).drop_duplicates("sha256")
    df.to_csv(out, index=False)
    return df.set_index("sha256")


def main(splits):
    feats = build_graph_feats()
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    man = man[man.keep_exact == 1].drop_duplicates("sha256").set_index("sha256")
    text_cache = {}
    for split in splits:
        for seed in range(5):
            sp = json.load(open(SPLITS / f"{split}_s{seed}.json"))
            need = sp["train"] + sp["test"]
            for s in need:
                if s not in text_cache:
                    text_cache[s] = file_text(man.loc[s])
            ytr = (man.loc[sp["train"], "label"] == "webshell").astype(int).values
            yte = (man.loc[sp["test"], "label"] == "webshell").astype(int).values
            preds = {}
            # hashed 1-2-gram counts + TF-IDF weighting (bounded memory; 2^18 buckets)
            hv = HashingVectorizer(token_pattern=TOKEN, lowercase=False, ngram_range=(1, 2), n_features=1 << 18,
                                   alternate_sign=False, norm=None, dtype=np.float32)
            tf = TfidfTransformer(sublinear_tf=True)
            hashed = lambda keys: sp_vstack([hv.transform([text_cache[s] for s in keys[i:i + 500]])
                                             for i in range(0, len(keys), 500)]).tocsr()
            Xtr = tf.fit_transform(hashed(sp["train"]))
            Xte = tf.transform(hashed(sp["test"]))
            lr = LogisticRegression(C=10, max_iter=3000).fit(Xtr, ytr)
            preds["tfidf_lr"] = lr.predict_proba(Xte)[:, 1]
            # XGBoost's hist builder does not fit 2^18 sparse columns in RAM: keep the 5k best by chi2, 32 bins
            sel = SelectKBest(chi2, k=5_000).fit(Xtr, ytr)
            xg = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, tree_method="hist", max_bin=32,
                                   random_state=seed, n_jobs=4).fit(sel.transform(Xtr), ytr)
            preds["tfidf_xgb"] = xg.predict_proba(sel.transform(Xte))[:, 1]
            Ftr = feats.reindex(sp["train"]).fillna(0).reset_index(drop=True)
            Fte = feats.reindex(sp["test"]).fillna(0).reset_index(drop=True)
            sx = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=seed, n_jobs=8)
            sx.fit(Ftr, ytr)
            preds["struct_xgb"] = sx.predict_proba(Fte)[:, 1]
            preds["rule_crit"] = (Fte.n_crit > 0).astype(float).values
            preds["rule_risk"] = ((Fte.n_crit + Fte.n_obf) > 0).astype(float).values
            preds["rule_risk_input"] = (((Fte.n_crit + Fte.n_obf) > 0) & (Fte.uses_input == 1)).astype(float).values
            for name, p in preds.items():
                m = metrics(yte, p >= 0.5)
                dump_json(dict(cfg=dict(name=f"bl_{split}_{name}_s{seed}", model=name, split=split, seed=seed),
                               test=m, pred=dict(sha=sp["test"], y=yte.tolist(), p=[round(float(x), 5) for x in p])),
                          RUNS / f"bl_{split}_{name}_s{seed}.json")
                print(f"{split:13s} s{seed} {name:16s} F1={m['f1']:.4f} P={m['precision']:.4f} R={m['recall']:.4f} FPR={m['fpr']:.4f}",
                      flush=True)
            if seed == 0:
                imp = sorted(zip(sx.feature_importances_, Ftr.columns), reverse=True)
                dump_json({c: float(v) for v, c in imp}, RUNS.parent / f"struct_importance_{split}.json")
                pass  # (hashed features: token names are not recoverable)


if __name__ == "__main__":
    main(sys.argv[1:] or ["paper_random", "clean_group", "cross_source"])
