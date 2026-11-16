#!/usr/bin/env bash
# Verify bytes without executing PHP; supports spaces in sample paths.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export GLARESHELL_REPO_ROOT="$ROOT"
python3 - <<'CHECK'
import csv, hashlib, os
from pathlib import Path
root = Path(os.environ["GLARESHELL_REPO_ROOT"])
data = Path(os.environ.get("GLARESHELL_DATA", root / "data"))
count = 0
for row in csv.DictReader(open(data / "manifests/manifest_all.csv")):
    if row["keep_exact"] != "1":
        continue
    base = root / "samples/raw" / row["label"] / row["source"]
    if row["source"] == "Cyc1e183__PHP-Webshell-Dataset":
        base /= "extracted"
    path = base / row["relpath"]
    if not path.resolve().is_relative_to(base.resolve()):
        raise SystemExit(f"Invalid sample path: {row['relpath']}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != row["sha256"]:
        raise SystemExit(f"SHA-256 mismatch: {path}")
    count += 1
print(f"OK: {count} samples verified")
CHECK
