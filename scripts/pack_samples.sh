#!/usr/bin/env bash
# Package the deduplicated corpus for private hand-over to graders: password-protected zip
# (password "infected", the usual malware-sharing convention) + SHA-256 checksums.
# NEVER upload the zip to a public location.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT=samples/glareshell_repro_samples.zip
python3 - <<'PY' > samples/filelist.txt
import csv
base = {"Cyc1e183__PHP-Webshell-Dataset": "samples/raw/webshell/Cyc1e183__PHP-Webshell-Dataset/extracted/"}
for r in csv.DictReader(open("data/manifests/manifest_all.csv")):
    if r["keep_exact"] == "1":
        print(base.get(r["source"], f"samples/raw/{r['label']}/{r['source']}/") + r["relpath"])
PY
rm -f "$OUT"
zip -q -P infected "$OUT" -@ < samples/filelist.txt
sha256sum "$OUT" > samples/glareshell_repro_samples.zip.sha256
cat samples/glareshell_repro_samples.zip.sha256
