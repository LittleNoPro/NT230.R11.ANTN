"""Parse the CC0 benign PHP construct fixtures; never execute fixture code.

Outputs exact nodes/edges, source hashes, pair comparisons and a small TeX table.
No classifier verdict is invented when the trained model is unavailable.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/construct_cases"
OUT = ROOT / "results/construct_cases"


def main():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="glareshell-constructs-") as temporary:
        listing, output = Path(temporary) / "inputs.tsv", Path(temporary) / "graphs.jsonl"
        listing.write_text("".join(f"{r['id']}\t{FIXTURES / r['file']}\n" for r in manifest["cases"]))
        subprocess.run(["php", "-d", "short_open_tag=On", str(ROOT / "src/php/extract_icfg.php"),
                        str(listing), str(output)], check=True, timeout=120, capture_output=True)
        records = {r["id"]: r for r in map(json.loads, output.read_text().splitlines())}
    if set(records) != {c["id"] for c in manifest["cases"]}:
        raise RuntimeError("not every fixture produced an extraction record")
    versions = {"php": subprocess.check_output(["php", "-r", "echo PHP_VERSION;"], text=True),
                "php_parser_commit": subprocess.check_output(["git", "-C", str(ROOT / "tools/vendor/PHP-Parser"), "rev-parse", "HEAD"], text=True).strip(),
                "lchecker_commit": subprocess.check_output(["git", "-C", str(ROOT / "tools/LChecker"), "rev-parse", "HEAD"], text=True).strip(),
                "extractor_sha256": hashlib.sha256((ROOT / "src/php/extract_icfg.php").read_bytes()).hexdigest()}
    for case in manifest["cases"]:
        rec = records[case["id"]]
        if not rec.get("ok"):
            raise RuntimeError(f"fixture extraction failed: {case['id']}: {rec.get('err')}")
        rec.pop("secs", None)
        rec.update(source_sha256=hashlib.sha256((FIXTURES / case["file"]).read_bytes()).hexdigest(),
                   label=case["label"], pair=case["pair"], classifier_status="not scored; this is an extractor study")
        (OUT / f"{case['id']}.json").write_text(json.dumps(rec, indent=2) + "\n")
        dot = ["digraph ICFG {", 'node [shape=box,fontname="monospace"];']
        for i, node in enumerate(rec["nodes"]):
            dot.append(f"n{i} [label={json.dumps(str(i) + ': ' + node[0] + ' [risk=' + str(node[2]) + ']')}];")
        dot += [f"n{a} -> n{b};" for a, b in rec["edges"]] + ["}"]
        (OUT / f"{case['id']}.dot").write_text("\n".join(dot) + "\n")
    rows = []
    for pair in manifest["pairs"]:
        a, b = [records[k] for k in pair["cases"]]
        pair["observed"] = {"nodes": [len(a["nodes"]), len(b["nodes"])],
                            "edges": [len(a["edges"]), len(b["edges"])],
                            "max_risk": [max((n[2] for n in r["nodes"]), default=0) for r in (a, b)],
                            "normalised_graph_equal": a["nodes"] == b["nodes"] and a["edges"] == b["edges"]}
        # Equality of normalised nodes ignores the raw pretty-printed field.
        pair["observed"]["normalised_graph_equal"] = (
            [[n[0], n[2]] for n in a["nodes"]] == [[n[0], n[2]] for n in b["nodes"]] and a["edges"] == b["edges"])
        o = pair["observed"]
        rows.append(f"{pair['title']} & {o['nodes'][0]}/{o['nodes'][1]} & {o['edges'][0]}/{o['edges'][1]} & "
                    f"{o['max_risk'][0]}/{o['max_risk'][1]} & {'yes' if o['normalised_graph_equal'] else 'no'} " + r"\\")
    result = dict(environment=versions, scope="22 benign synthetic extractor fixtures; no detection metrics", pairs=manifest["pairs"])
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    table = [r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule", r"Pair (A/B) & Nodes & Edges & Max risk & Same graph \\ \midrule", *rows, r"\bottomrule", r"\end{tabular}"]
    (ROOT / "results/tables/construct_cases.tex").write_text("\n".join(table) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
