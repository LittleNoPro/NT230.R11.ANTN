"""Generate report numbers and compact tables from a verified v2 evidence directory.

Run from anywhere: python report/render_metrics.py --evidence evaluation/v2
Uses the standard library; no samples, GPU or training packages are needed.
"""
import argparse
import ast
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report/generated"


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def latex(s):
    return str(s).replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("$", r"\$")


def table(name, header, records, spec):
    content = [rf"\begin{{tabular}}{{@{{}}{spec}@{{}}}}", r"\toprule", " & ".join(header) + r" \\ \midrule"]
    content += [" & ".join(r) + r" \\" for r in records]
    content += [r"\bottomrule", r"\end{tabular}"]
    (OUT / name).write_text("\n".join(content) + "\n")


def generate(evidence):
    evidence = evidence.resolve()
    data, results = evidence / "data", evidence / "results"
    check = read(results / "evaluation_check.json")
    if check["status"] != "passed" or check["checked_runs"] != 346:
        raise ValueError("A complete, validated 346-run v2 evaluation is required")
    for relative, expected in read(results / "provenance.json")["sha256"].items():
        path = evidence / relative
        if not path.resolve().is_relative_to(evidence) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Changed or invalid evidence: {relative}")
    summary, environment = read(results / "summary.json"), read(evidence / "environment.json")
    manifest = rows(data / "manifests/manifest_all.csv")
    kept = {r["sha256"]: r for r in manifest if r["keep_exact"] == "1"}
    hard = rows(data / "manifests/manifest_hard.csv")
    values = {}

    def number(key, value, digits=3, percent=False):
        if isinstance(value, int):
            values[key] = f"{value:,}"
        elif not math.isfinite(value):
            values[key] = "--"
        else:
            values[key] = f"{value * (100 if percent else 1):.{digits}f}" + (r"\%" if percent else "")
            if key.startswith("p_") and 0 < abs(value) < 10 ** (-digits):
                mantissa, exponent = f"{value:.2e}".split("e")
                values[key] = mantissa + r"\times10^{" + str(int(exponent)) + "}"

    def estimate(key, pair, digits=3, percent=False):
        number(key, pair[0], digits, percent)
        number(key + "_ci", pair[1], digits, percent)

    def ci(pair, digits=3):
        if not math.isfinite(pair[0]):
            return "--"
        return f"{pair[0]:.{digits}f}" + (r"$\pm$" + f"{pair[1]:.{digits}f}" if math.isfinite(pair[1]) else "")

    number("checked_runs", check["checked_runs"])
    number("checked_splits", check["checked_splits"])
    number("main_samples", len(kept))
    number("sources", 24)
    for key in ("php", "gpu", "python", "torch", "cuda_runtime"):
        values[key] = latex(environment[key].splitlines()[0])
    # Reuse the original paper values without importing the analysis dependencies.
    paper = {}
    for node in ast.parse((ROOT / "src/analyze.py").read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("PAPER_T2", "PAPER_T4") for t in node.targets):
            paper[node.targets[0].id] = ast.literal_eval(node.value)
    records = []
    embedding_names = {"glove": "GloVe", "w2v_c": "W2V CBOW", "w2v_s": "W2V Skip-gram",
                       "d2v_m": "D2V DM", "d2v_w": "D2V DBOW", "fasttext": "FastText"}
    for group, names in (("table2", embedding_names),
                         ("table4", {"gcn": "GCN", "gin": "GIN", "gat": "GAT"})):
        for key, name in names.items():
            current = summary[group][key]
            for metric in ("f1", "precision", "recall", "fpr"):
                estimate(f"{group}_{key}_{metric}", current[metric])
            original = paper["PAPER_T2" if group == "table2" else "PAPER_T4"][key][4]
            records.append([name, ci(current["f1"]), f"{original:.3f}", f"{current['f1'][0]-original:+.3f}"])
    OUT.mkdir(parents=True, exist_ok=True)
    table("reproduction.tex", ["Setting", "Ours: F1", "Paper", r"$\Delta$"], records, "lrrr")
    models = {"GlareShell GCN": "gcn", "GlareShell GAT": "gat", "TF-IDF + LR": "lr",
              "TF-IDF + XGBoost": "xgb", "Graph-stats + XGBoost": "struct", "Rule: any risky call": "rule"}
    records = []
    for name, alias in models.items():
        protocols = summary["protocols"][name]
        for protocol, short in (("paper_random", "paper"), ("clean_group", "clean"), ("cross_source", "cross")):
            agg = protocols[protocol]["agg"] if short == "cross" else protocols[protocol]
            for metric in ("f1", "precision", "recall", "fpr"):
                estimate(f"{alias}_{short}_{metric}", agg[metric])
                if metric == "fpr":
                    estimate(f"{alias}_{short}_fpr_percent", agg[metric], 2, True)
        cross = protocols["cross_source"]["agg"]
        records.append([name.replace("GlareShell ", ""), ci(protocols["paper_random"]["f1"]),
                        ci(protocols["clean_group"]["f1"]), f"{100*cross['fpr'][0]:.2f}" + r"\%",
                        ci(cross["recall"], 2)])
    table("protocols_compact.tex", ["Model", "F1 random", "F1 clean", "FPR unseen", "Recall unseen"], records, "lrrrr")
    records = []
    for protocol in ("paper_random", "clean_group", "cross_source"):
        for name, protocols in summary["protocols"].items():
            item = protocols[protocol]["agg"] if protocol == "cross_source" else protocols[protocol]
            records.append([latex(protocol), name] + [ci(item[k], 4) for k in ("precision", "recall", "f1", "fpr")])
    table("protocols_full.tex", ["Protocol", "Model", "Precision", "Recall", "F1", "FPR"], records, "llrrrr")
    for protocol in ("paper_random", "clean_group", "cross_source"):
        split = read(data / f"splits/{protocol}_s0.json")
        for part in ("train", "val", "test"):
            for label in ("benign", "webshell"):
                number(f"{protocol}_{part}_{label}", sum(kept[k]["label"] == label for k in split[part]))
        for label in ("benign", "webshell"):
            number(f"{protocol}_all_{label}", sum(kept[k]["label"] == label for p in split.values() for k in p))
    for label in ("webshell", "benign"):
        estimate(f"leakage_{label}", summary["leakage_paper_random"][label], 1, True)
    for key, value in summary["webshell_clusters"].items():
        number("cluster_" + key, int(value))
    for key, value in summary["timing"].items():
        number(key, value, 1)
    for key, item in summary["sweep"].items():
        number(f"sweep_{key}_min", min(item["f1"]))
        number(f"sweep_{key}_max", max(item["f1"]))
    for group, alias in (("paper_random (GCN, Table-2 setting)", "paper"),
                         ("clean_group (GAT, Table-3 setting)", "clean")):
        for variant, metrics in summary["ablation"][group].items():
            for metric in ("f1", "recall", "fpr"):
                estimate(f"abl_{alias}_{variant}_{metric}", metrics[metric])
    for name, alias in (("GlareShell GAT", "gat"), ("TF-IDF + LR", "lr")):
        for protocol in ("clean_group", "cross_source"):
            for key, value in summary["operating_points"][name][protocol].items():
                estimate(f"{alias}_{protocol}_{key}", value)
    for key, item in summary["significance"].items():
        name = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_")
        number("p_" + name, item["p_paired_t"], 4)
    aliases = {"p_gat_gcn": "paper_random: GAT vs GCN (Table 4)",
               "p_gat_gin": "paper_random: GAT vs GIN (Table 4)",
               "p_fast_d2v": "paper_random: FastText vs D2V-w (Table 2)",
               "p_abl_paper": "paper_random: n+w vs none (GCN, Fig. 8)",
               "p_abl_clean": "clean_group: n+w vs none (GAT, Fig. 8)"}
    for alias, key in aliases.items():
        number(alias, summary["significance"][key]["p_paired_t"], 4)
    hard_summary = summary["hard_benign"]
    number("hard_train", hard_summary["n_train_added"])
    number("hard_test", sum(r["subset"] == "hard_test" for r in hard))
    number("probe_count", sum(r["subset"] == "probe" for r in hard))
    hard_counts = [len(read(data / f"splits/base_s{seed}.json")["test"]) for seed in range(5)]
    number("hard_test_min", min(hard_counts))
    number("hard_test_max", max(hard_counts))
    for model, alias in (("GAT", "gat"), ("TF-IDF + LR", "lr")):
        for kind in ("base", "aug"):
            for label, key, percent in (("all benign files: FPR", "fpr", True),
                                        ("all webshells: recall", "recall", False),
                                        ("unseen large projects (\\xs): FPR", "cross_fpr", True),
                                        ("12 benign probe scripts: flagged", "probes", False)):
                estimate(f"hard_{alias}_{kind}_{key}", hard_summary["results"][model][kind][label], 2 if percent else 3, percent)
        for label, key in (("all benign files: FPR", "fpr"), ("all webshells: recall", "recall")):
            number(f"p_hard_{alias}_{key}", hard_summary["paired"][model][label]["p_paired_t"], 4)
        novel_key = next(k for k in hard_summary["results"][model]["base"] if "novel webshells" in k)
        for kind in ("base", "aug"):
            estimate(f"hard_{alias}_{kind}_novel_recall", hard_summary["results"][model][kind][novel_key])
        number(f"p_hard_{alias}_novel_recall", hard_summary["paired"][model][novel_key]["p_paired_t"], 4)
    records = []
    hard_groups = (("All benign: FPR", "all benign files: FPR", True),
                   ("All webshells: recall", "all webshells: recall", False),
                   ("Novel webshells: recall", novel_key, False),
                   ("Unseen projects: FPR", "unseen large projects (\\xs): FPR", True),
                   ("12 probes: flagged", "12 benign probe scripts: flagged", False))
    for title, key, percent in hard_groups:
        row = [title]
        for model in ("GAT", "TF-IDF + LR"):
            for kind in ("base", "aug"):
                value = hard_summary["results"][model][kind][key][0]
                row.append(f"{100*value:.2f}" + r"\%" if percent else f"{value:.2f}")
        records.append(row)
    table("hard_compact.tex", ["Test group", "GAT base", "aug", "LR base", "aug"], records, "lrrrr")
    demo = read(results / "runs/final_demo_gat.json")
    for metric in ("f1", "fpr", "precision", "recall"):
        number("demo_" + metric, demo["test"][metric])
    probabilities, flagged = {}, {}
    for line in (results / "probe_benign.txt").read_text().splitlines():
        match = re.match(r"(WEBSHELL|benign)\s+p=([.0-9]+)\s+n_stmt=\d+\s+(.+\.php)$", line)
        if match:
            name = Path(match[3]).name
            probabilities[name], flagged[name] = float(match[2]), match[1] == "WEBSHELL"
    text_probs = read(results / "probe_tfidf.json")
    if probabilities.keys() != text_probs.keys():
        raise ValueError("GAT and text probe files differ")
    number("demo_probes_flagged", sum(flagged.values()))
    number("lr_probes_flagged", sum(p >= .5 for p in text_probs.values()))
    descriptions = {"hello.php": "escaped greeting", "contact_form.php": "validated contact form",
                    "download.php": "whitelisted download", "export_csv.php": "PDO query to CSV",
                    "guestbook.php": "append-only guestbook", "image_upload.php": "MIME/size-checked upload",
                    "login.php": "PDO and password verification", "ping_tool.php": "validated IP and escaped argument",
                    "router.php": "static route table", "template_render.php": "template rendering",
                    "cleanup_cron.php": "remove old cache files", "json_api.php": "JSON to-do API"}
    def probability(p, is_flagged):
        value = f"{p:.3f}"
        return rf"\textbf{{{value}}}" if is_flagged else value
    records = [[latex(name), probability(probabilities[name], flagged[name]), probability(text_probs[name], text_probs[name] >= .5), descriptions[name]]
               for name in sorted(probabilities)]
    table("probes.tex", ["Script", "GAT", "TF-IDF+LR", "Purpose"], records, "lrrl")
    runs = [read(p) for p in (results / "runs").glob("*.json")]
    gnn = [r for r in runs if "gnn" in r["cfg"]]
    number("gnn_runs", len(gnn))
    number("gnn_training_hours", sum(r["secs_train"] for r in gnn) / 3600, 2)
    number("embedding_hours", sum(r["secs_embedding"] for r in gnn) / 3600, 2)
    number("mixed_clusters", len({r["cluster"] for r in rows(data / "manifests/clusters.csv") if r["cluster_mixed"] == "1"}))
    def pvalue(value):
        if 0 < value < 1e-4:
            a, b = f"{value:.2e}".split("e")
            text = a + r"\times10^{" + str(int(b)) + "}"
        else:
            text = f"{value:.4f}"
        return "$p=" + text + "$"

    def verdict(text, kind):
        return "\\" + {"yes": "repro", "no": "notrepro", "extra": "improved"}[kind] + "{" + text + "}"

    significance_rows = []
    for comparison_name, item in summary["significance"].items():
        protocol, comparison_name = comparison_name.split(": ", 1)
        significance_rows.append([latex(protocol), latex(comparison_name),
                                  f"{item['diff'][0]:+.4f}" + r"$\pm$" + f"{item['diff'][1]:.4f}",
                                  pvalue(item["p_paired_t"]).replace("$p=", "$", 1),
                                  f"{item['mcnemar_sig']}/{item['n']}",
                                  "yes" if item["p_paired_t"] < .05 else "no"])
    table("significance.tex", ["Protocol", "Comparison (A vs B)", r"$\Delta$F1 (A$-$B)",
                              r"Paired-$t$ $p$", r"McNemar $p<.05$", "Significant"],
          significance_rows, "llrrrr")

    best_embedding = max(summary["table2"], key=lambda k: summary["table2"][k]["f1"][0])
    score_range = [v["f1"][0] for v in summary["table4"].values()]
    significant_gat = all(summary["significance"][aliases[k]]["diff"][0] > 0 and
                          summary["significance"][aliases[k]]["p_paired_t"] < .05 for k in ("p_gat_gcn", "p_gat_gin"))
    abl = summary["significance"][aliases["p_abl_paper"]]
    comparison = summary["significance"]["clean_group: GAT vs TF-IDF + LR"]
    improvement = hard_summary["paired"]["GAT"]["all benign files: FPR"]
    records = [
        ["High F1 with graph pipeline", f"Table-4 means {min(score_range):.3f}--{max(score_range):.3f}; rebuilt corpus, five seeds",
         verdict("Comparable level" if max(score_range) >= .95 else "Not reproduced", "yes" if max(score_range) >= .95 else "no")],
        ["FastText ranks first among embeddings", latex(embedding_names[best_embedding]) + " achieves the highest mean F1",
         verdict("Same top embedding" if best_embedding == "fasttext" else "Different top embedding",
                 "yes" if best_embedding == "fasttext" else "no")],
        ["GAT advantage over GCN/GIN", "Paired GAT--GCN " + pvalue(summary["significance"][aliases["p_gat_gcn"]]["p_paired_t"]) +
         "; GAT--GIN " + pvalue(summary["significance"][aliases["p_gat_gin"]]["p_paired_t"]),
         verdict("Supported here" if significant_gat else "Not established", "yes" if significant_gat else "no")],
        ["Normalisation+risk F1 gain (random)", f"Full minus raw {abl['diff'][0]:+.4f}; " + pvalue(abl["p_paired_t"]),
         verdict("Supported here" if abl["diff"][0] > 0 and abl["p_paired_t"] < .05 else "Not established",
                 "yes" if abl["diff"][0] > 0 and abl["p_paired_t"] < .05 else "no")],
        ["Universal dimension/window optimum", "Three-seed descriptive curves on this benchmark", verdict("Not established", "no")],
        ["GAT vs. lexical baseline (clean)", f"GAT minus LR F1 {comparison['diff'][0]:+.4f}; " + pvalue(comparison["p_paired_t"]),
         verdict("GAT higher" if comparison["diff"][0] > 0 and comparison["p_paired_t"] < .05 else
                 ("Text higher" if comparison["diff"][0] < 0 and comparison["p_paired_t"] < .05 else "Unresolved"),
                 "yes" if comparison["diff"][0] > 0 and comparison["p_paired_t"] < .05 else "no")],
        ["Auxiliary benign-data intervention", f"GAT FPR difference {improvement['diff_aug_minus_base'][0]:+.4f}; " + pvalue(improvement["p_paired_t"]) +
         f"; novel recall {hard_summary['results']['GAT']['base'][novel_key][0]:.2f}" + r"$\to$" +
         f"{hard_summary['results']['GAT']['aug'][novel_key][0]:.2f}",
         verdict("Lower FPR; recall cost" if improvement["diff_aug_minus_base"][0] < 0 and improvement["p_paired_t"] < .05 else "Inconclusive",
                 "extra" if improvement["diff_aug_minus_base"][0] < 0 and improvement["p_paired_t"] < .05 else "no")],
        ["Duplicate/source control and construct study", "Corrected v2 clusters/splits; 22 original CC0 fixtures; graph limitations retained", verdict("Extended", "extra")],
        ["Industrial server effectiveness", "Static public corpora only; no deployment or runtime traces", verdict("Not evaluated", "no")],
        ["Independent human label audit", "150 restored files; 300 unfilled decisions; no agreement/error-rate claim", verdict("Pending", "no")]
    ]
    content = [r"\begin{tabularx}{\linewidth}{@{}p{.27\linewidth}Xl@{}}", r"\toprule",
               r"Claim / item & Measured v2 evidence & Assessment \\ \midrule"]
    content += [" & ".join(r) + r" \\" for r in records]
    content += [r"\bottomrule", r"\end{tabularx}"]
    (OUT / "verdict.tex").write_text("\n".join(content) + "\n")
    # Illustrative error cases use observed predictions and numeric extractor
    # metadata only; they do not adjudicate source labels or infer causation.
    graph_stats = {r["sha256"]: r for r in rows(data / "processed/graph_stats.csv")}
    cases = []
    for run_name, error, predicate in (
            ("t4_gat_s0", "Paper FN", lambda st: int(st["n_nodes"]) == 0 or int(st["parse_error"]) > 0),
            ("cross_gat_s0", "Cross FP", lambda st: int(st["n_crit"]) + int(st["n_obf"]) == 0),
            ("cross_gat_s0", "Cross FN", lambda st: int(st["n_crit"]) + int(st["n_obf"]) == 0),
            ("t4_gat_s0", "Capped FN", lambda st: int(st["truncated"]) > 0)):
        prediction = read(results / f"runs/{run_name}.json")["pred"]
        positive = error.endswith("FN")
        candidates = []
        for sha, y, score in zip(prediction["sha"], prediction["y"], prediction["p"]):
            if y != int(positive) or (score >= .5) == bool(y):
                continue
            stats = graph_stats[sha]
            if predicate(stats):
                candidates.append((score, sha, stats))
        if not candidates:
            continue
        score, sha, stats = sorted(candidates, reverse=not positive)[0]
        if any(c["sha256"] == sha for c in cases):
            continue
        flags = []
        if int(stats["ok"]) == 0:
            flags.append("extraction failure")
        if int(stats["parse_error"]):
            flags.append("recovered syntax error")
        if int(stats["truncated"]):
            flags.append("truncated")
        if not int(stats["n_crit"]) + int(stats["n_obf"]):
            flags.append("no flagged API")
        cases.append(dict(case=error, run=run_name, sha256=sha, label=kept[sha]["label"],
                          source=kept[sha]["source"], relpath=kept[sha]["relpath"],
                          score=score, nodes=int(stats["n_nodes"]), observations=flags))
    records = [[c["case"], r"\makecell[l]{" + latex(c["source"].replace("__", "/")) + r"\\\texttt{" + c["sha256"][:12] + "}}",
                c["label"], f"{c['score']:.3f}", f"{c['nodes']}; " + "; ".join(c["observations"])] for c in cases]
    table("error_cases.tex", ["Case", "Source / SHA prefix", "Label proxy", "Score", "Nodes; observations"], records, "llrrl")
    (OUT / "error_cases.json").write_text(json.dumps(dict(selection="seed-0 errors selected by extractor flags and score; illustrative, not random or independently adjudicated", cases=cases), indent=2) + "\n")
    output = ["% Generated from verified v2 evidence by report/render_metrics.py; do not edit numbers by hand.",
              r"\providecommand{\result}[1]{\ifcsname result@#1\endcsname\csname result@#1\endcsname\else\PackageError{v2metrics}{Unknown result key: #1}{Regenerate verified v2 report values.}\fi}"]
    output += [rf"\expandafter\def\csname result@{key}\endcsname{{{value}}}" for key, value in sorted(values.items())]
    (OUT / "metrics.tex").write_text("\n".join(output) + "\n")
    (OUT / "metrics.json").write_text(json.dumps(values, indent=2) + "\n")
    print(f"Generated {len(values)} report values and eight tables from {evidence}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=ROOT / "evaluation/v2")
    generate(parser.parse_args().evidence)
