#!/usr/bin/env bash
# Package the deduplicated corpus for private hand-over to graders: password-protected zip
# (password "infected", the usual malware-sharing convention) + SHA-256 checksums.
# NEVER upload the zip to a public location.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${GLARESHELL_SAMPLE_ARCHIVE:-samples/glareshell_repro_samples.zip}"
export GLARESHELL_REPO_ROOT="$ROOT"
python3 - <<'PY' > samples/filelist.txt
import csv, os
from pathlib import Path
root = Path(os.environ["GLARESHELL_REPO_ROOT"])
data = Path(os.environ.get("GLARESHELL_DATA", root / "data"))
base = {"Cyc1e183__PHP-Webshell-Dataset": "samples/raw/webshell/Cyc1e183__PHP-Webshell-Dataset/extracted/"}
for r in csv.DictReader(open(data / "manifests/manifest_all.csv")):
    if r["keep_exact"] == "1":
        print(base.get(r["source"], f"samples/raw/{r['label']}/{r['source']}/") + r["relpath"])
hard = data / "manifests/manifest_hard.csv"
if hard.exists():
    for r in csv.DictReader(hard.open()):
        prefix = "tests/probe_benign/" if r["source"] == "probe_benign" else f"samples/raw/benign_small/{r['source']}/"
        print(prefix + r["relpath"])
PY
rm -f "$OUT"
zip -q -P infected "$OUT" -@ < samples/filelist.txt
sha256sum "$OUT" > samples/glareshell_repro_samples.zip.sha256
cat samples/glareshell_repro_samples.zip.sha256
