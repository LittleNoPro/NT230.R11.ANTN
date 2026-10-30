#!/usr/bin/env bash
# Verify that every sample kept by the manifest is present and byte-identical (SHA-256).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 - <<'PY' > /tmp/glareshell_sha256sums.txt
import csv
base = {"Cyc1e183__PHP-Webshell-Dataset": "samples/raw/webshell/Cyc1e183__PHP-Webshell-Dataset/extracted/"}
for r in csv.DictReader(open("data/manifests/manifest_all.csv")):
    if r["keep_exact"] == "1":
        print(f"{r['sha256']}  {base.get(r['source'], 'samples/raw/' + r['label'] + '/' + r['source'] + '/')}{r['relpath']}")
PY
sha256sum --quiet -c /tmp/glareshell_sha256sums.txt && echo "OK: $(wc -l < /tmp/glareshell_sha256sums.txt) samples verified"
