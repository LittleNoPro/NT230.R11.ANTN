"""GlareShell demo detector: score PHP files, or watch a directory like the paper's file-system monitor.

    python detect.py FILE_OR_DIR [...]          # one-shot scan
    python detect.py --watch DIR [--interval 2]  # re-scan new / modified .php files

Static only: files are parsed by the PHP extractor, never executed or included.
Needs models/fasttext.kv and models/gat.pt (python train_final.py).
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

from common import ROOT
from train_gnn import GlareNet, make_data

PHP_EXT = {".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".inc"}
RISK = {0: "normal", 1: "obfuscated", 2: "critical"}


def extract(paths):
    """Run the PHP ICFG extractor on a batch of files -> {path: record}."""
    with tempfile.TemporaryDirectory() as td:
        lst, out = Path(td) / "l.tsv", Path(td) / "o.jsonl"
        lst.write_text("".join(f"{i}\t{Path(p).resolve()}\n" for i, p in enumerate(paths)))
        subprocess.run(["php", "-d", "short_open_tag=On", str(ROOT / "src/php/extract_icfg.php"), str(lst), str(out)],
                       capture_output=True, timeout=120)
        recs = {}
        if out.exists():
            for line in open(out):
                r = json.loads(line)
                recs[paths[int(r["id"])]] = r
    return recs


class Detector:
    def __init__(self, threshold=0.5):
        from gensim.models import KeyedVectors
        ck = torch.load(ROOT / "models/gat.pt", map_location="cpu", weights_only=False)
        c = ck["cfg"]
        self.wv = KeyedVectors.load(str(ROOT / "models/fasttext.kv"))  # ~45 s: gensim rebuilds word vectors from n-grams
        self.model = GlareNet(np.zeros((1, ck["emb_dim"]), np.float32), c["variant"] == "nw", c["gnn"], c["hidden"],
                              c["layers"], c["heads"])
        self.model.load_state_dict(ck["state"], strict=False)
        self.model.eval()
        self.threshold = threshold

    @torch.no_grad()
    def score(self, rec):
        nodes = rec.get("nodes", []) if rec.get("ok") else []
        # per-file lookup table: row 0 = zero vector, row i+1 = FastText vector of statement i
        table = np.zeros((len(nodes) + 1, self.wv.vector_size), np.float32)
        for i, n in enumerate(nodes):
            table[i + 1] = self.wv[n[0]]
        g = dict(norm=np.arange(len(nodes), dtype=np.int32), risk=np.array([n[2] for n in nodes], np.int8),
                 edges=np.asarray(rec.get("edges", []), np.int32).reshape(-1, 2).T)
        d = make_data(g, "norm", 0)
        d.batch = torch.zeros(d.num_nodes, dtype=torch.long)
        self.model.table = torch.from_numpy(table)
        p = float(torch.softmax(self.model(d), 1)[0, 1])
        reasons = [f"[{RISK[n[2]]}] {n[1][:100]}" for n in nodes if n[2] > 0][:5]
        notes = []
        if not nodes:
            notes.append("empty ICFG (unparsable or no code) -> decision unreliable")
        if rec.get("parse_error"):
            notes.append("syntax errors recovered")
        if rec.get("truncated"):
            notes.append("ICFG truncated at 2000 statements")
        return p, reasons, notes

    def report(self, paths):
        recs = extract([str(p) for p in paths])
        for p in paths:
            rec = recs.get(str(p), {"ok": False})
            prob, reasons, notes = self.score(rec)
            verdict = "WEBSHELL" if prob >= self.threshold else "benign"
            print(f"{verdict:8s} p={prob:.3f} n_stmt={len(rec.get('nodes', []))} {p}")
            for r in reasons:
                print(f"           {r}")
            for n in notes:
                print(f"           note: {n}")
            sys.stdout.flush()


def php_files(target):
    t = Path(target)
    if t.is_file():
        return [t]
    return sorted(p for p in t.rglob("*") if p.is_file() and p.suffix.lower() in PHP_EXT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--watch")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    det = Detector(a.threshold)
    for t in a.targets:
        det.report(php_files(t))
    if a.watch:
        # polling stand-in for the paper's watchdog FileCreatedEvent / FileModifiedEvent filter
        seen = {p: p.stat().st_mtime for p in php_files(a.watch)}
        print(f"watching {a.watch} ({len(seen)} existing files ignored); Ctrl-C to stop", flush=True)
        while True:
            time.sleep(a.interval)
            cur = {p: p.stat().st_mtime for p in php_files(a.watch)}
            changed = [p for p, m in cur.items() if seen.get(p) != m]
            if changed:
                det.report(changed)
            seen = cur


if __name__ == "__main__":
    main()
