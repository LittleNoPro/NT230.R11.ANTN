"""Manual label audit: blinded, double-reviewed sample of the corpus (docs/AUDIT_PROTOCOL.md).

  python label_audit.py sample   # -> samples/audit/<id>.txt (blinded copies), data/audit/sheet_<auditor>.csv, key
  python label_audit.py score    # filled sheets -> agreement, label-error rates -> results/tables/label_audit.tex

Strata (sampled in this order, no file twice):
  fn    webshells GAT misses (mean p < 0.5 over the clean_group + cross_source seeds)
  fp    benign files GAT flags (mean p >= 0.5)
  risky benign files with at least one critical call (confusable case 1 of the label guide)
  ws    random webshells
  bn    random benign files
Each file is reviewed by two of the three auditors (rotating pairs); auditors do not see the current label.
Copies are plain .txt files in samples/ (outside git, never served or executed).
"""
import json
import shutil
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from baselines import RAW
from common import DATA, PROC, RESULTS, ROOT, RUNS, dump_json, wilson

AUDITORS = ["Tu", "Vu", "Duc"]
STRATA = {"fn": 25, "fp": 25, "risky": 25, "ws": 50, "bn": 25}
OUT = DATA / "audit"
FILES = ROOT / "samples" / "audit"
VERDICTS = {"webshell", "benign", "unsure"}


def _path(r):
    base = RAW / "webshell" / "Cyc1e183__PHP-Webshell-Dataset" / "extracted" if r.source.startswith("Cyc1e183") \
        else RAW / r.label / r.source
    return base / r.relpath


def _gat_mean_p():
    ps = defaultdict(list)
    for f in sorted(RUNS.glob("clean_gat_s*.json")) + sorted(RUNS.glob("cross_gat_s*.json")):
        pred = json.load(open(f))["pred"]
        for s, p in zip(pred["sha"], pred["p"]):
            ps[s].append(p)
    return {s: float(np.mean(v)) for s, v in ps.items()}


def sample():
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    man = man[man.keep_exact == 1].drop_duplicates("sha256").set_index("sha256")
    feats = pd.read_csv(PROC / "graph_feats.csv", index_col="sha256")
    man = man.join(feats[["n_nodes", "n_crit", "uses_input"]], how="left")
    gp = _gat_mean_p()
    man["gat_p"] = pd.Series(gp)
    rng = np.random.default_rng(2024)
    pools = {
        "fn": man[(man.label == "webshell") & (man.gat_p < 0.5)],
        "fp": man[(man.label == "benign") & (man.gat_p >= 0.5)],
        "risky": man[(man.label == "benign") & (man.n_crit > 0)],
        "ws": man[man.label == "webshell"],
        "bn": man[man.label == "benign"],
    }
    taken, rows = set(), []
    for stratum, n in STRATA.items():
        pool = [s for s in pools[stratum].index if s not in taken]
        pick = rng.choice(pool, size=min(n, len(pool)), replace=False)
        taken.update(pick)
        rows += [dict(sha256=s, stratum=stratum, pool_size=len(pools[stratum])) for s in pick]
    key = pd.DataFrame(rows).sample(frac=1, random_state=2024).reset_index(drop=True)  # shuffle: id reveals nothing
    key.insert(0, "audit_id", [f"A{i:03d}" for i in range(len(key))])
    key = key.join(man[["label", "source", "relpath", "size", "gat_p"]], on="sha256")
    key["auditors"] = [",".join(AUDITORS[j % 3] for j in (i, i + 1)) for i in range(len(key))]
    FILES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for r in key.itertuples():
        shutil.copyfile(_path(man.loc[r.sha256].rename(r.sha256)), FILES / f"{r.audit_id}.txt")
    key.to_csv(OUT / "audit_key.csv", index=False)
    for a in AUDITORS:
        mine = key[key.auditors.str.contains(a)]
        pd.DataFrame(dict(audit_id=mine.audit_id, file=[f"samples/audit/{i}.txt" for i in mine.audit_id],
                          verdict="", case="", notes="")).to_csv(OUT / f"sheet_{a}.csv", index=False)
        print(a, len(mine), "files")
    print(key.stratum.value_counts().to_string())


def kappa(a, b):
    labs = sorted(set(a) | set(b))
    a, b = np.asarray(a), np.asarray(b)
    po = (a == b).mean()
    pe = sum((a == l).mean() * (b == l).mean() for l in labs)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def score():
    key = pd.read_csv(OUT / "audit_key.csv").set_index("audit_id")
    votes = defaultdict(dict)
    for a in AUDITORS:
        s = pd.read_csv(OUT / f"sheet_{a}.csv", dtype=str).fillna("")
        s["verdict"] = s.verdict.str.strip().str.lower()
        bad = s[~s.verdict.isin(VERDICTS)]
        if len(bad):
            sys.exit(f"sheet_{a}.csv: {len(bad)} rows without a valid verdict (e.g. {bad.audit_id.iloc[0]})")
        for r in s.itertuples():
            votes[r.audit_id][a] = r.verdict
    pairs = {}
    for i, a in enumerate(AUDITORS):
        for b in AUDITORS[i + 1:]:
            ids = [k for k, v in votes.items() if a in v and b in v]
            pairs[f"{a}-{b}"] = dict(n=len(ids), kappa=round(kappa([votes[k][a] for k in ids], [votes[k][b] for k in ids]), 3))
    key["audit"] = [(lambda v: v[0] if len(set(v)) == 1 else "disagree")(list(votes[k].values())) for k in key.index]
    adj = OUT / "adjudication.csv"  # optional: audit_id,verdict after discussing disagreements
    if adj.exists():
        a = pd.read_csv(adj).set_index("audit_id").verdict.str.strip().str.lower()
        key.loc[a.index, "audit"] = a
    key.to_csv(OUT / "audit_result.csv")
    rows, out = [], dict(pairs=pairs, strata={})
    names = dict(fn="GAT false negatives", fp="GAT false positives", risky="risky benign",
                 ws="random webshells", bn="random benign")
    for st in STRATA:
        d = key[key.stratum == st]
        decided = d[d.audit.isin(["webshell", "benign"])]
        wrong = int((decided.audit != decided.label).sum())
        lo, hi = (max(0.0, x) for x in wilson(wrong, len(decided))) if len(decided) else (0.0, 0.0)
        out["strata"][st] = dict(n=len(d), decided=len(decided), unsure=int((d.audit == "unsure").sum()),
                                 disagree=int((d.audit == "disagree").sum()), label_wrong=wrong, ci=[lo, hi])
        rows.append(f"{names[st]} & {int(d.pool_size.iloc[0])} & {len(d)} & {len(decided)} & {wrong} & "
                    f"{wrong / max(len(decided), 1):.2f} [{lo:.2f}, {hi:.2f}] \\\\")
    dump_json(out, RESULTS / "label_audit.json")
    tex = ("\\begin{tabular}{@{}lrrrrl@{}}\n\\toprule\nStratum & Pool & Audited & Decided & Label wrong & "
           "Rate [95\\% CI] \\\\ \\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
    (RESULTS / "tables" / "label_audit.tex").write_text(tex)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"sample": sample, "score": score}[sys.argv[1]]()
