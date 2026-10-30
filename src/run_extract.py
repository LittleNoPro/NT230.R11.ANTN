"""Run the PHP ICFG extractor over every manifest file kept by exact dedup.

Output: data/processed/icfg/part-XXXX.jsonl (git-ignored: contains code fragments of malware).
"""
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "samples" / "raw"
OUT = ROOT / "data" / "processed" / "icfg"
SRC_DIRS = {
    "Cyc1e183__PHP-Webshell-Dataset": RAW / "webshell" / "Cyc1e183__PHP-Webshell-Dataset" / "extracted",
}


def abs_path(r):
    base = SRC_DIRS.get(r.source, RAW / r.label / r.source)
    return base / r.relpath


def run_chunk(i, rows):
    part = OUT / f"part-{i:04d}.jsonl"
    if part.exists():
        return i, "cached"
    lst = OUT / f"part-{i:04d}.tsv"
    lst.write_text("".join(f"{r.sha256}\t{abs_path(r)}\n" for r in rows))
    tmp = part.with_suffix(".tmp")
    try:
        p = subprocess.run(["php", "-d", "short_open_tag=On", str(ROOT / "src/php/extract_icfg.php"), str(lst), str(tmp)],
                           capture_output=True, text=True, timeout=60 * 30)
        tmp.rename(part)
        return i, p.returncode
    except subprocess.TimeoutExpired:
        return i, "timeout"
    finally:
        lst.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--chunk", type=int, default=150)
    ap.add_argument("--missing", action="store_true", help="re-run only samples absent from existing parts, 1 file/process")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(ROOT / "data/manifests/manifest_all.csv")
    m = m[m.keep_exact == 1].sort_values("sha256")
    start = 0
    if a.missing:  # a PHP segfault (deeply nested expressions) kills a whole chunk; isolate per file
        import json
        done = {json.loads(l)["id"] for p in OUT.glob("part-*.jsonl") for l in open(p)}
        m = m[~m.sha256.isin(done)]
        a.chunk, start = 1, 10000
    rows = list(m.itertuples())
    chunks = [rows[i:i + a.chunk] for i in range(0, len(rows), a.chunk)]
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(tqdm(ex.map(lambda t: run_chunk(*t), enumerate(chunks, start)), total=len(chunks)))
    bad = [r for r in res if r[1] not in (0, "cached")]
    print("chunks", len(chunks), "non-zero", bad[:20])


if __name__ == "__main__":
    main()
