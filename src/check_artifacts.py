"""Dependency-free integrity checks on committed research evidence; no PHP execution."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    provenance = json.loads((ROOT / "results/provenance.json").read_text())
    for name, expected in provenance["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"historical input or prediction changed: {name}")
    man = {r["sha256"]: r for r in csv.DictReader(open(ROOT / "data/manifests/manifest_all.csv")) if r["keep_exact"] == "1"}
    man.update({r["sha256"]: r for r in csv.DictReader(open(ROOT / "data/manifests/manifest_hard.csv"))})
    clusters = {r["sha256"]: r["cluster"] for r in csv.DictReader(open(ROOT / "data/manifests/clusters.csv"))}
    splits = list((ROOT / "data/splits").glob("*_s*.json"))
    for path in splits:
        s = json.loads(path.read_text())
        for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
            if set(s[a]) & set(s[b]):
                raise ValueError(f"sample overlap: {path} {a}/{b}")
            if not path.name.startswith("paper_random"):
                ca, cb = [{clusters[x] for x in s[k] if x in clusters} for k in (a, b)]
                if ca & cb:
                    raise ValueError(f"recorded cluster overlap: {path} {a}/{b}")
        if path.name.startswith("cross_source"):
            if {man[x]["source"] for x in s["train"]} & {man[x]["source"] for x in s["test"]}:
                raise ValueError(f"source overlap: {path}")
    runs = list((ROOT / "results/runs").glob("*.json"))
    for path in runs:
        r = json.loads(path.read_text())
        p, cfg = r["pred"], r["cfg"]
        if len({len(p[k]) for k in ("sha", "y", "p")}) != 1:
            raise ValueError(f"prediction length mismatch: {path}")
        s = json.loads((ROOT / "data/splits" / f"{cfg['split']}_s{cfg['seed']}.json").read_text())
        if p["sha"] != s["test"]:
            raise ValueError(f"test ids differ from recorded split: {path}")
        counts = Counter()
        for sha, y, probability in zip(p["sha"], p["y"], p["p"]):
            if y != int(man[sha]["label"] == "webshell") or not 0 <= probability <= 1:
                raise ValueError(f"invalid prediction: {path} {sha}")
            counts[("tp" if y else "fp") if probability >= .5 else ("fn" if y else "tn")] += 1
        if any(counts[k] != r["test"][k] for k in ("tp", "tn", "fp", "fn")):
            raise ValueError(f"confusion counts differ: {path}")
        tp, tn, fp, fn = (counts[k] for k in ("tp", "tn", "fp", "fn"))
        def div(a, b):
            return a / b if b else float("nan")
        expected = dict(precision=div(tp, tp + fp), recall=div(tp, tp + fn),
                        tnr=div(tn, tn + fp), fpr=div(fp, tn + fp),
                        acc=div(tp + tn, tp + tn + fp + fn), f1=div(2 * tp, 2 * tp + fp + fn))
        for metric, value in expected.items():
            actual = r["test"][metric]
            if not ((math.isnan(value) and math.isnan(actual)) or math.isclose(value, actual, abs_tol=1e-9)):
                raise ValueError(f"metric mismatch: {path} {metric}")
    audit = {p.stem: Counter(r["verdict"].strip() or "pending" for r in csv.DictReader(p.open()))
             for p in sorted((ROOT / "data/audit").glob("sheet_*.csv"))}
    result = dict(status="passed", checked_runs=len(runs), checked_splits=len(splits),
                  historical_hashes=len(provenance["sha256"]), audit_status=audit,
                  scope="saved predictions and recorded legacy clusters; does not establish absence of unclustered near-duplicates or rerun model training")
    (ROOT / "results/artifact_check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
