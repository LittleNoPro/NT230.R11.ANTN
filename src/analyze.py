"""Aggregate runs into report tables (results/tables/*.tex), figures (report/figures/*.pdf),
an error taxonomy and results/summary.json."""
import glob
import json
import re
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import DATA, PROC, RESULTS, ROOT, RUNS, SPLITS, mean_ci, metrics, wilson

TAB = RESULTS / "tables"
FIG = ROOT / "report" / "figures"
SHOW = ["precision", "recall", "tnr", "acc", "f1"]
PAPER_T2 = {"glove": [0.8905, 0.9335, 0.8862, 0.9078, 0.9136], "w2v_c": [0.9216, 0.9595, 0.8998, 0.9303, 0.9373],
            "w2v_s": [0.9024, 0.9552, 0.8986, 0.9116, 0.9355], "d2v_m": [0.9138, 0.9496, 0.8794, 0.9201, 0.9309],
            "d2v_w": [0.9236, 0.9568, 0.8930, 0.9286, 0.9293], "fasttext": [0.9329, 0.9615, 0.9174, 0.9405, 0.9454]}
PAPER_T4 = {"gcn": [0.9591, 0.9795, 0.9334, 0.9614, 0.9675], "gin": [0.9676, 0.9878, 0.9516, 0.9718, 0.9767],
            "gat": [0.9739, 0.9952, 0.9712, 0.9837, 0.9887]}
NAMES = {"glove": "GloVe", "w2v_c": "W2V-c", "w2v_s": "W2V-s", "d2v_m": "D2V-m", "d2v_w": "D2V-w",
         "fasttext": "FastText", "gcn": "GCN", "gin": "GIN", "gat": "GAT", "none": "none", "n": "n", "nw": "n+w",
         "tfidf_lr": "TF-IDF + LR", "tfidf_xgb": "TF-IDF + XGBoost", "struct_xgb": "Graph-stats + XGBoost",
         "rule_crit": "Rule: critical call", "rule_risk": "Rule: any risky call",
         "rule_risk_input": "Rule: risky call + request input"}


def load(pattern):
    out = []
    for f in sorted(glob.glob(str(RUNS / f"{pattern}.json"))):
        out.append(json.load(open(f)))
    return out


def agg(runs):
    """metric -> (mean, ci half width) over seeds."""
    return {m: mean_ci([r["test"][m] for r in runs]) for m in SHOW + ["fpr"]} | {"n_seeds": len(runs)}


def fmt(mc, digits=4):
    m, h = mc
    if m != m:
        return "--"
    return f"{m:.{digits}f}" + (f"$\\pm${h:.{digits}f}" if h == h else "")


def latex_table(rows, header, path, n_text=1):
    """Write a complete tabular (booktabs); the first n_text columns are left-aligned text."""
    TAB.mkdir(parents=True, exist_ok=True)
    spec = "l" * n_text + "r" * (len(header) - n_text)
    lines = [rf"\begin{{tabular}}{{@{{}}{spec}@{{}}}}", r"\toprule", " & ".join(header) + r" \\ \midrule"]
    lines += [" & ".join(r) + r" \\" for r in rows] + [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")


def table2(S):
    rows = []
    for m in PAPER_T2:
        runs = load(f"t2_{m}_s?")
        if not runs:
            continue
        a = agg(runs)
        S["table2"][m] = a
        rows.append([NAMES[m]] + [fmt(a[k]) for k in SHOW] + [f"{PAPER_T2[m][4]:.4f}", f"{a['f1'][0] - PAPER_T2[m][4]:+.4f}"])
    latex_table(rows, ["Method", "Precision", "Recall", "TNR", "Acc", "F1", "F1 (paper)", r"$\Delta$F1"], TAB / "table2.tex")


def table4(S):
    rows = []
    for g in PAPER_T4:
        runs = load(f"t4_{g}_s?")
        if not runs:
            continue
        a = agg(runs)
        S["table4"][g] = a
        rows.append([NAMES[g]] + [fmt(a[k]) for k in SHOW] + [f"{PAPER_T4[g][4]:.4f}", f"{a['f1'][0] - PAPER_T4[g][4]:+.4f}"])
    latex_table(rows, ["Model", "Precision", "Recall", "TNR", "Acc", "F1", "F1 (paper)", r"$\Delta$F1"], TAB / "table4.tex")


def ablation(S):
    groups = {"paper_random (GCN, Table-2 setting)": {"none": "abl_none_s?", "n": "abl_n_s?", "nw": "t2_fasttext_s?"},
              "clean_group (GAT, Table-3 setting)": {"none": "clean_abl_none_s?", "n": "clean_abl_n_s?", "nw": "clean_gat_s?"}}
    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=False)
    for ax, (gname, pats) in zip(axes, groups.items()):
        S["ablation"][gname] = {}
        xs = np.arange(len(SHOW))
        for i, (v, pat) in enumerate(pats.items()):
            runs = load(pat)
            if not runs:
                continue
            a = agg(runs)
            S["ablation"][gname][v] = a
            rows.append([gname.split(" ")[0].replace("_", r"\_"), NAMES[v]] + [fmt(a[k]) for k in SHOW + ["fpr"]])
            ax.bar(xs + (i - 1) * 0.27, [a[k][0] for k in SHOW], 0.27, yerr=[a[k][1] if a[k][1] == a[k][1] else 0 for k in SHOW],
                   label=NAMES[v], capsize=2)
        ax.set_xticks(xs, ["Prec.", "Rec.", "TNR", "Acc", "F1"])
        ax.set_title(gname, fontsize=9)
        ax.set_ylim(0.6, 1.0)
        ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "ablation.pdf")
    plt.close(fig)
    latex_table(rows, ["Protocol", "Variant", "Precision", "Recall", "TNR", "Acc", "F1", "FPR"], TAB / "ablation.tex", n_text=2)


def sweeps(S):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3))
    for ax, (key, vals, pat, base) in zip(axes, [
            ("dim", [20, 40, 60, 80, 100, 120], "dim{v}_s?", 100),
            ("window", [2, 3, 4, 5, 6, 7], "win{v}_s?", 5)]):
        ms, hs, xs = [], [], []
        for v in vals:
            runs = load(pat.format(v=v)) if v != base else [r for r in load("t2_fasttext_s?") if r["cfg"]["seed"] < 3]
            if not runs:
                continue
            m, h = mean_ci([r["test"]["f1"] for r in runs])
            xs.append(v); ms.append(m); hs.append(0 if h != h else h)
        S["sweep"][key] = dict(x=xs, f1=ms, ci=hs)
        ax.errorbar(xs, ms, yerr=hs, marker="o", capsize=3)
        ax.set_xlabel("embedding dimension" if key == "dim" else "context window size")
        ax.set_ylabel("F1 (FastText + GCN, 3 seeds)")
        ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(FIG / "sweeps.pdf")
    plt.close(fig)


def protocols(S):
    """Same models under the three protocols + baselines."""
    rows = []
    models = [("GlareShell GCN", {"paper_random": "t4_gcn_s?", "clean_group": "clean_gcn_s?", "cross_source": "cross_gcn_s?"}),
              ("GlareShell GAT", {"paper_random": "t4_gat_s?", "clean_group": "clean_gat_s?", "cross_source": "cross_gat_s?"})]
    for b in ["tfidf_lr", "tfidf_xgb", "struct_xgb", "rule_crit", "rule_risk", "rule_risk_input"]:
        models.append((NAMES[b], {sp: f"bl_{sp}_{b}_s?" for sp in ("paper_random", "clean_group", "cross_source")}))
    for name, pats in models:
        S["protocols"][name] = {}
        r = [name]
        for sp in ("paper_random", "clean_group"):
            runs = load(pats[sp])
            a = agg(runs) if runs else None
            S["protocols"][name][sp] = a
            r += [fmt(a["f1"]) if a else "--", fmt(a["fpr"]) if a else "--"]
        runs = load(pats["cross_source"])
        if runs:
            # cross-source: mean +- CI over seeds (as elsewhere); seed-0 Wilson CIs show the sampling
            # uncertainty of the fixed test set (only 18 novel webshells) and are kept in summary.json
            a = agg(runs)
            t = runs[0]["test"]
            lo, hi = wilson(t["fp"], t["fp"] + t["tn"])
            rlo, rhi = wilson(t["tp"], t["tp"] + t["fn"])
            S["protocols"][name]["cross_source"] = dict(agg=a, seed0=t, fpr_wilson=(lo, hi), recall_wilson=(rlo, rhi))
            r += [fmt(a["fpr"]), fmt(a["recall"], 3)]
        else:
            r += ["--", "--"]
        rows.append(r)
    latex_table(rows, ["Model", "F1 (paper split)", "FPR (paper split)", "F1 (clean)", "FPR (clean)",
                       "FPR held-out benign", "Recall novel webshells"], TAB / "protocols.tex")


def per_source_fpr(S):
    man = pd.read_csv(DATA / "manifests/manifest_all.csv").drop_duplicates("sha256").set_index("sha256")
    rows, out = [], {}
    for name, pat in [("GlareShell GAT", "cross_gat_s?"), ("GlareShell GCN", "cross_gcn_s?"),
                      ("TF-IDF + LR", "bl_cross_source_tfidf_lr_s?"), ("Rule: any risky call", "bl_cross_source_rule_risk_s?")]:
        runs = load(pat)
        if not runs:
            continue
        per = defaultdict(list)
        for r in runs:
            df = pd.DataFrame(dict(sha=r["pred"]["sha"], y=r["pred"]["y"], p=r["pred"]["p"]))
            df["source"] = man.loc[df.sha, "source"].values
            for s, d in df[df.y == 0].groupby("source"):
                per[s].append(float((d.p >= 0.5).mean()))
        out[name] = {s: mean_ci(v) for s, v in per.items()}
    srcs = sorted({s for v in out.values() for s in v})
    for s in srcs:
        n = int(((man.subset == "heldout") & (man.source == s) & (man.label == "benign") & (man.keep_ws == 1)).sum())
        rows.append([s.replace("__", "/").replace("_", r"\_"), str(n)] + [fmt(out[m][s], 4) if s in out[m] else "--" for m in out])
    latex_table(rows, ["Held-out project", "Files"] + list(out), TAB / "per_source_fpr.tex")
    S["per_source_fpr"] = out


def leakage_and_data(S):
    cl = pd.read_csv(DATA / "manifests/clusters.csv")
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    leak = []
    for seed in range(5):
        sp = json.load(open(SPLITS / f"paper_random_s{seed}.json"))
        c = cl.set_index("sha256").cluster
        trc = set(c.loc[sp["train"]])
        te = cl.set_index("sha256").loc[sp["test"]]
        leak.append(te.assign(l=te.cluster.isin(trc)).groupby("label").l.mean().to_dict())
    S["leakage_paper_random"] = {k: mean_ci([d[k] for d in leak]) for k in ("webshell", "benign")}
    # cluster sizes among paper webshells
    w = cl[(cl.label == "webshell") & (cl.subset == "paper")]
    sizes = w.groupby("cluster").size()
    S["webshell_clusters"] = dict(files=int(len(w)), clusters=int(len(sizes)), singletons=int((sizes == 1).sum()),
                                  largest=int(sizes.max()), files_in_clusters_ge5=int(sizes[sizes >= 5].sum()))
    fig, ax = plt.subplots(figsize=(4.5, 3))
    vc = sizes.value_counts().sort_index()
    ax.bar(vc.index.astype(str)[:15], vc.values[:15])
    ax.set_xlabel("near-duplicate cluster size"); ax.set_ylabel("# clusters (webshell, paper sources)")
    ax.set_yscale("log"); fig.tight_layout(); fig.savefig(FIG / "cluster_sizes.pdf"); plt.close(fig)
    # dedup funnel per source
    rows = []
    for (lab, sub, src), d in man.groupby(["label", "subset", "source"]):
        rows.append([lab, sub, src.replace("__", "/").replace("_", r"\_"), str(len(d)), str(int(d.is_php.sum())),
                     str(int(d.keep_exact.sum())), str(int(d.keep_ws.sum()))])
    latex_table(rows, ["Label", "Subset", "Source", "PHP-ext files", "contain \\texttt{<?}", "exact dedup", "ws dedup"],
                TAB / "dataset_funnel.tex", n_text=3)
    st = pd.read_csv(PROC / "graph_stats.csv")
    g = st.groupby(["label", "subset"]).agg(n=("sha256", "size"), fail=("ok", lambda s: int((s == 0).sum())),
                                           parse=("parse_error", "sum"), empty=("n_nodes", lambda s: int((s == 0).sum())),
                                           trunc=("truncated", "sum"), med=("n_nodes", "median"),
                                           p90=("n_nodes", lambda s: s.quantile(.9)), secs=("secs", "mean"))
    S["extraction"] = json.loads(g.reset_index().to_json(orient="records"))
    latex_table([[a, b] + [f"{v:.0f}" if k != "secs" else f"{v*1000:.1f}" for k, v in r.items()] for (a, b), r in g.iterrows()],
                ["Label", "Subset", "Files", "Crash", "Parse err.", "Empty ICFG", "Truncated", "Median nodes",
                 "P90 nodes", "ms/file"], TAB / "extraction.tex", n_text=2)
    ws = st[(st.label == "webshell") & (st.subset == "paper")]
    fig, ax = plt.subplots(figsize=(4.5, 3))
    ax.hist(ws.n_nodes.clip(upper=2000), bins=50)
    ax.set_xlabel("# PHP statements in pruned ICFG (capped 2000)"); ax.set_ylabel("# webshell files")
    fig.tight_layout(); fig.savefig(FIG / "stmt_dist.pdf"); plt.close(fig)


def error_taxonomy(S):
    """Tag every test error of the best model (GAT) with machine-checkable causes."""
    feats = pd.read_csv(PROC / "graph_feats.csv").set_index("sha256")
    man = pd.read_csv(DATA / "manifests/manifest_all.csv").drop_duplicates("sha256").set_index("sha256")
    dyn = {}
    want = set()
    for pat in ("t4_gat_s?", "clean_gat_s?", "cross_gat_s?"):
        for r in load(pat):
            for s, y, p in zip(r["pred"]["sha"], r["pred"]["y"], r["pred"]["p"]):
                if (p >= 0.5) != y:
                    want.add(s)
    for part in sorted((PROC / "icfg").glob("part-*.jsonl")):
        for line in open(part):
            if line[7:71] in want:  # line starts with {"id":"<sha256>"
                rr = json.loads(line)
                raws = [n[1] for n in rr.get("nodes", [])]
                dyn[rr["id"]] = dict(dyn_call=any(re.search(r"(^|[^\w>:])\$\w+\s*\(", x) for x in raws),
                                     long_str=any(re.search(r"'[A-Za-z0-9+/=]{60,}", x) for x in raws),
                                     superglobal=any("$_" in x for x in raws))

    def tags(s, y):
        if s not in feats.index:  # extractor crashed, no graph features
            return ["extractor crash"]
        f, d = feats.loc[s], dyn.get(s, {})
        t = []
        if f.n_nodes == 0:
            t.append("empty ICFG")
        if f.parse_error:
            t.append("parse error (recovered)")
        if f.truncated:
            t.append("ICFG truncated at 2000 nodes")
        if f.n_nodes and f.n_nodes < 5:
            t.append("tiny ICFG (<5 statements)")
        if y == 1:
            if f.n_crit + f.n_obf == 0:
                t.append("no risky built-in call" + (" (dynamic call $f())" if d.get("dyn_call") else ""))
            if d.get("long_str"):
                t.append("encoded payload string")
            if not d.get("superglobal"):
                t.append("no request input in ICFG")
        else:
            if f.n_crit:
                t.append("benign uses critical call")
            elif f.n_obf:
                t.append("benign uses callback/eval-like call")
            if d.get("superglobal"):
                t.append("benign reads request input")
        return t or ["no tag"]

    out, rows = {}, []
    for proto, pat in (("paper_random", "t4_gat_s?"), ("clean_group", "clean_gat_s?"), ("cross_source", "cross_gat_s?")):
        c = {"FN": Counter(), "FP": Counter()}
        n = {"FN": 0, "FP": 0}
        src = {"FN": Counter(), "FP": Counter()}
        for r in load(pat):
            for s, y, p in zip(r["pred"]["sha"], r["pred"]["y"], r["pred"]["p"]):
                if (p >= 0.5) == y:
                    continue
                k = "FN" if y == 1 else "FP"
                n[k] += 1
                src[k][man.loc[s, "origin"] if k == "FN" else man.loc[s, "source"]] += 1
                for t in tags(s, y):
                    c[k][t] += 1
        out[proto] = dict(n=n, tags={k: dict(v.most_common()) for k, v in c.items()},
                          sources={k: dict(v.most_common(6)) for k, v in src.items()})
        for k in ("FN", "FP"):
            for t, v in c[k].most_common(5):
                rows.append([proto.replace("_", r"\_"), k, t.replace("$", r"\$").replace("_", r"\_"), str(v),
                             f"{100 * v / max(n[k], 1):.0f}\\%"])
    latex_table(rows, ["Protocol", "Error", "Tag (non-exclusive)", "Count (5 seeds)", "Share"], TAB / "errors.tex", n_text=3)
    S["errors"] = out


def confusion(S):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3))
    for ax, (title, pat) in zip(axes, [("paper split", "t4_gat_s0"), ("clean split", "clean_gat_s0"),
                                       ("cross-source", "cross_gat_s0")]):
        runs = load(pat)
        if not runs:
            continue
        t = runs[0]["test"]
        M = np.array([[t["tn"], t["fp"]], [t["fn"], t["tp"]]])
        S["confusion"][title] = M.tolist()
        ax.imshow(M, cmap="Blues")
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(M[i, j]), ha="center", va="center", color="black")
        ax.set_xticks([0, 1], ["pred benign", "pred webshell"]); ax.set_yticks([0, 1], ["benign", "webshell"])
        ax.set_title(f"GAT, {title}, seed 0", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "confusion.pdf"); plt.close(fig)


def _preds(pat):
    """seed -> DataFrame(sha, y, p) for the runs matching pat."""
    out = {}
    for r in load(pat):
        out[r["cfg"].get("seed", 0)] = pd.DataFrame(dict(sha=r["pred"]["sha"], y=r["pred"]["y"], p=r["pred"]["p"])).set_index("sha")
    return out


def _bl(split, name):
    return f"bl_{split}_{name}_s?"


def significance(S):
    """Paired comparisons on identical test sets: F1 difference over seeds (paired t) + exact McNemar per seed."""
    from scipy import stats
    comps = [("paper_random", "GAT vs GCN (Table 4)", "t4_gat_s?", "t4_gcn_s?"),
             ("paper_random", "GAT vs GIN (Table 4)", "t4_gat_s?", "t4_gin_s?"),
             ("paper_random", "FastText vs D2V-w (Table 2)", "t2_fasttext_s?", "t2_d2v_w_s?"),
             ("paper_random", "n+w vs none (GCN, Fig. 8)", "t2_fasttext_s?", "abl_none_s?"),
             ("clean_group", "n+w vs none (GAT, Fig. 8)", "clean_gat_s?", "clean_abl_none_s?"),
             ("paper_random", "GAT vs TF-IDF + LR", "t4_gat_s?", _bl("paper_random", "tfidf_lr")),
             ("clean_group", "GAT vs TF-IDF + LR", "clean_gat_s?", _bl("clean_group", "tfidf_lr")),
             ("cross_source", "GAT vs TF-IDF + LR", "cross_gat_s?", _bl("cross_source", "tfidf_lr"))]
    rows, out = [], {}
    for split, name, pa, pb in comps:
        A, B = _preds(pa), _preds(pb)
        seeds = sorted(set(A) & set(B))
        if len(seeds) < 2:
            continue
        d, sig, fa, fb = [], 0, [], []
        for sd in seeds:
            a, b = A[sd], B[sd].loc[A[sd].index]
            ya, yb = (a.p >= .5).astype(int), (b.p >= .5).astype(int)
            f_a, f_b = metrics(a.y, ya)["f1"], metrics(a.y, yb)["f1"]
            fa.append(f_a); fb.append(f_b); d.append(f_a - f_b)
            ca, cb = ya == a.y, yb == a.y
            n01, n10 = int((ca & ~cb).sum()), int((~ca & cb).sum())  # exact McNemar = binomial test on discordant pairs
            sig += n01 + n10 > 0 and stats.binomtest(n01, n01 + n10, 0.5).pvalue < 0.05
        m, h = mean_ci(d)
        pv = float(stats.ttest_rel(fa, fb).pvalue) if np.std(d) > 0 else 1.0
        out[f"{split}: {name}"] = dict(diff=(m, h), p_paired_t=pv, mcnemar_sig=int(sig), n=len(seeds))
        rows.append([split.replace("_", r"\_"), name, f"{m:+.4f}$\\pm${h:.4f}", f"{pv:.3f}", f"{sig}/{len(seeds)}",
                     "yes" if (pv < 0.05 and abs(m) > 0) else "no"])
    latex_table(rows, ["Protocol", "Comparison (A vs B)", r"$\Delta$F1 (A$-$B)", "paired-$t$ $p$", "McNemar $p<.05$",
                       "Significant"], TAB / "significance.tex", n_text=2)
    S["significance"] = out


def operating_points(S):
    """ROC/PR summaries per seed and recall at fixed false-positive budgets (test-set oracle thresholds)."""
    from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
    models = [("GlareShell GAT", {"paper_random": "t4_gat_s?", "clean_group": "clean_gat_s?", "cross_source": "cross_gat_s?"}),
              ("GlareShell GCN", {"paper_random": "t4_gcn_s?", "clean_group": "clean_gcn_s?", "cross_source": "cross_gcn_s?"})]
    for b in ("tfidf_lr", "tfidf_xgb", "struct_xgb"):
        models.append((NAMES[b], {sp: _bl(sp, b) for sp in ("paper_random", "clean_group", "cross_source")}))
    rows, out = [], {}
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3))
    for name, pats in models:
        out[name] = {}
        for sp in ("clean_group", "cross_source"):
            P = _preds(pats[sp])
            if not P:
                continue
            auc, ap, r01, r1 = [], [], [], []
            for sd, d in sorted(P.items()):
                auc.append(roc_auc_score(d.y, d.p)); ap.append(average_precision_score(d.y, d.p))
                fpr, tpr, _ = roc_curve(d.y, d.p)
                r01.append(float(tpr[fpr <= 0.001].max())); r1.append(float(tpr[fpr <= 0.01].max()))
                if sd == 0:
                    ax = axes[0 if sp == "clean_group" else 1]
                    ax.plot(np.maximum(fpr, 1e-5), tpr, label=name, lw=1.2)
            a = dict(auc=mean_ci(auc), ap=mean_ci(ap), recall_fpr01=mean_ci(r01), recall_fpr1=mean_ci(r1))
            out[name][sp] = a
            rows.append([name, sp.replace("_", r"\_"), fmt(a["auc"]), fmt(a["ap"]), fmt(a["recall_fpr01"], 3), fmt(a["recall_fpr1"], 3)])
    for ax, t in zip(axes, ("clean split", "cross-source (unseen projects)")):
        ax.set_xscale("log"); ax.set_xlim(1e-4, 1); ax.set_ylim(0, 1.01); ax.grid(alpha=.3)
        ax.set_xlabel("false-positive rate (log)"); ax.set_ylabel("true-positive rate"); ax.set_title(f"ROC, {t}, seed 0", fontsize=9)
    axes[1].legend(fontsize=7, loc="lower right")
    fig.tight_layout(); fig.savefig(FIG / "roc.pdf"); plt.close(fig)
    latex_table(rows, ["Model", "Protocol", "ROC-AUC", "PR-AUC (AP)", "Recall @ FPR 0.1\\%", "Recall @ FPR 1\\%"],
                TAB / "operating_points.tex", n_text=2)
    S["operating_points"] = out


def origin_loo(S):
    """Leave-one-collection-out: recall on the held-out collection's webshells, FPR on clean benign test files."""
    models = [("GlareShell GAT", "loo_{o}_gat_s?"), ("GlareShell GCN", "loo_{o}_gcn_s?")]
    models += [(NAMES[b], "bl_loo_{o}_" + b + "_s?") for b in ("tfidf_lr", "tfidf_xgb", "struct_xgb", "rule_risk_input")]
    rows, out = [], {}
    for o, n_name in (("tennc", "tennc/webshell"), ("bartblaze", "bartblaze/PHP-backdoors"), ("xl7dev", "xl7dev/WebShell")):
        out[o] = {}
        for name, pat in models:
            runs = load(pat.format(o=o))
            if not runs:
                continue
            a = agg(runs)
            out[o][name] = a
            n_ws = runs[0]["test"]["tp"] + runs[0]["test"]["fn"]
            rows.append([f"{n_name} ({n_ws})", name, fmt(a["recall"], 3), fmt(a["fpr"]), fmt(a["f1"])])
    latex_table(rows, ["Held-out collection (\\#webshells)", "Model", "Recall (unseen collection)", "FPR", "F1"],
                TAB / "origin_loo.tex", n_text=2)
    S["origin_loo"] = out


def hard_benign(S):
    """Improvement experiment: train without (base) / with (aug) small benign apps; same test files."""
    hard = DATA / "manifests/manifest_hard.csv"
    if not hard.exists():
        return
    mh = pd.read_csv(hard)
    cg = set(json.load(open(SPLITS / "clean_group_s0.json"))["test"])
    groups = {"clean test: webshell recall": ("cg", 1), "clean test: FPR": ("cg", 0),
              "unseen large projects (\\xs): FPR": ("xs", 0), "18 novel webshells: recall": ("xs", 1)}
    for src, name in (("opnsense__core", "OPNsense core"), ("osTicket__osTicket", "osTicket"), ("mybb__mybb", "MyBB")):
        groups[f"unseen small app {name}: FPR"] = (src, 0)
    groups["12 benign probe scripts: flagged"] = ("probe_benign", 0)
    groups["Tiny File Manager: $p$(webshell)"] = ("prasathmani__tinyfilemanager", None)
    hsrc = dict(zip(mh.sha256, mh.source))
    out, rows = {}, []
    for model, pat in (("GAT", "hard_{k}_gat_s?"), ("TF-IDF + LR", "bl_{k}_tfidf_lr_s?")):
        res = {}
        for k in ("base", "aug"):
            per = defaultdict(list)
            for r in load(pat.format(k=k)):
                d = pd.DataFrame(dict(sha=r["pred"]["sha"], y=r["pred"]["y"], p=r["pred"]["p"]))
                d["g"] = [hsrc.get(x, "cg" if x in cg else "xs") for x in d.sha]
                for gname, (g, y) in groups.items():
                    sub = d[d.g == g] if y is None else d[(d.g == g) & (d.y == y)]
                    if not len(sub):
                        continue
                    if y is None:
                        v = float(sub.p.iloc[0])
                    elif g == "probe_benign":
                        v = float((sub.p >= .5).sum())
                    else:  # recall (webshells) or FPR (benign)
                        v = float((sub.p >= .5).mean())
                    per[gname].append(v)
            res[k] = {g: mean_ci(v) for g, v in per.items()}
        out[model] = res
    for g in groups:  # one row per test group: GAT base/aug, TF-IDF base/aug
        d = 1 if "probe" in g else (3 if "recall" in g or "$p$" in g else 4)
        rows.append([g] + [fmt(out[m][k][g], d) for m in out for k in ("base", "aug")])
    n_files = mh[mh.subset != "hard_train"].groupby("source").size().to_dict()
    S["hard_benign"] = dict(results=out, n_test_files=n_files, n_train_added=int((mh.subset == "hard_train").sum()))
    latex_table(rows, ["Test group", "GAT base", "GAT aug", "TF-IDF+LR base", "TF-IDF+LR aug"],
                TAB / "hard_benign.tex", n_text=1)


def timing(S):
    st = pd.read_csv(PROC / "graph_stats.csv")
    S["timing"] = dict(extract_ms_mean=float(st.secs.mean() * 1000), extract_ms_p95=float(st.secs.quantile(.95) * 1000))


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    S = defaultdict(dict)
    for fn in (leakage_and_data, table2, table4, ablation, sweeps, protocols, per_source_fpr, confusion, error_taxonomy,
               significance, operating_points, origin_loo, hard_benign, timing):
        try:
            fn(S)
        except Exception as e:  # keep producing the other artefacts while runs are still in progress
            print(f"[{fn.__name__}] skipped: {type(e).__name__}: {e}")
    (RESULTS / "summary.json").write_text(json.dumps(S, indent=1, default=float))
    print("wrote", RESULTS / "summary.json")


if __name__ == "__main__":
    main()
