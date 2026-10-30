"""Build the sample manifest (provenance, hashes, first-seen dates, exact dedup).

Reads only file bytes from samples/raw (never executes anything) and writes
data/manifests/manifest_all.csv: one row per candidate file, with `keep` marking
the representative after exact-hash deduplication.

Subsets:
  paper   – the sources listed in Table 1 of the paper (ysrc is reachable only through
            the Cyc1e183 aggregate, the original repo was deleted from GitHub)
  heldout – extra sources added for the dataset track (cross-source evaluation)
"""
import csv
import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "samples" / "raw"
OUT = ROOT / "data" / "manifests" / "manifest_all.csv"
PHP_EXT = re.compile(r"\.(php[3-7]?|phtml|inc)$", re.I)

# (label, source dir, subset, priority for dedup: lower wins)
SOURCES = [
    ("webshell", "webshell/Cyc1e183__PHP-Webshell-Dataset/extracted", "paper", 0),
    ("webshell", "webshell/bartblaze__PHP-backdoors", "paper", 1),
    ("webshell", "webshell/tennc__webshell", "paper", 2),
    ("webshell", "webshell/JohnTroony__php-webshells", "paper", 3),
    ("webshell", "webshell/BlackArch__webshells", "heldout", 10),
    ("webshell", "webshell/xl7dev__WebShell", "heldout", 11),
    ("benign", "benign/WordPress__WordPress", "paper", 0),
    ("benign", "benign/doorgets__CMS", "paper", 1),
    ("benign", "benign/laravel__laravel", "paper", 2),
    ("benign", "benign/PHPMailer__PHPMailer", "paper", 3),
    ("benign", "benign/drupal__drupal", "paper", 4),
    ("benign", "benign/laravel__framework", "heldout", 10),
    ("benign", "benign/phpmyadmin__phpmyadmin", "heldout", 11),
    ("benign", "benign/joomla__joomla-cms", "heldout", 12),
    ("benign", "benign/matomo-org__matomo", "heldout", 13),
]


def git_first_seen(repo: Path) -> dict:
    """path -> ISO date of the commit that first added it (empty for shallow clones)."""
    if not (repo / ".git").exists():
        return {}
    shallow = (repo / ".git" / "shallow").exists()
    if shallow:
        return {}
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--reverse", "--diff-filter=A", "--name-only", "--format=@@%aI"],
        capture_output=True, text=True, errors="replace").stdout
    seen, date = {}, None
    for line in out.splitlines():
        if line.startswith("@@"):
            date = line[2:12]
        elif line.strip() and line not in seen:
            seen[line] = date
    return seen


def ws_norm_hash(b: bytes) -> str:
    return hashlib.sha256(re.sub(rb"\s+", b"", b)).hexdigest()


def main():
    rows = []
    md5_origin = {}  # md5 -> first non-aggregate webshell repo containing it
    for label, rel, subset, prio in SOURCES:
        base = RAW / rel
        repo_root = base if (base / ".git").exists() else base.parent
        dates = git_first_seen(repo_root)
        for p in sorted(base.rglob("*")):
            if not p.is_file() or ".git" in p.parts:
                continue
            if not PHP_EXT.search(p.name):
                continue
            b = p.read_bytes()
            md5 = hashlib.md5(b).hexdigest()
            relp = str(p.relative_to(repo_root))
            src = rel.split("/")[1]
            if label == "webshell" and prio > 0:
                md5_origin.setdefault(md5, src)
            rows.append(dict(
                label=label, source=src, subset=subset, prio=prio, relpath=relp,
                sha256=hashlib.sha256(b).hexdigest(), md5=md5, ws_hash=ws_norm_hash(b),
                size=len(b), is_php=int(b"<?" in b), first_seen=dates.get(relp, ""),
            ))
    # provenance for the aggregate (Cyc1e183 names files by md5, no origin column)
    for r in rows:
        r["origin"] = md5_origin.get(r["md5"], "unknown") if r["prio"] == 0 and r["label"] == "webshell" else r["source"]
    # Two dedup levels, both label-consistent and restricted to real PHP:
    #   keep_exact – first copy per SHA-256 (what the paper reports: "after deduplication")
    #   keep_ws    – first copy per whitespace-normalised hash (stricter, used by our clean split)
    rows.sort(key=lambda r: (r["subset"] != "paper", r["prio"], r["relpath"]))
    for key, flag in (("sha256", "keep_exact"), ("ws_hash", "keep_ws")):
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r)
        for grp in groups.values():
            labels = {g["label"] for g in grp}
            for i, g in enumerate(grp):
                g[flag] = int(i == 0 and len(labels) == 1 and g["is_php"] == 1 and g["size"] > 0)
                if key == "ws_hash":
                    g["dup_of"] = "" if i == 0 else grp[0]["sha256"][:16]
                    g["label_conflict"] = int(len(labels) > 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["sha256", "md5", "ws_hash", "label", "subset", "source", "origin", "relpath", "size", "is_php",
            "first_seen", "dup_of", "label_conflict", "keep_exact", "keep_ws", "prio"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    import collections
    c = collections.Counter((r["label"], r["subset"], r["keep_exact"], r["keep_ws"]) for r in rows)
    for k in sorted(c):
        print(k, c[k])


if __name__ == "__main__":
    main()
