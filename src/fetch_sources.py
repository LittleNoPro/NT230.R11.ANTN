"""Fetch exact upstream revisions from sources.lock.tsv; never execute samples."""
import argparse
import csv
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "samples/raw"


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true", help="check checkouts against the lock without network access")
    args = ap.parse_args()
    with (ROOT / "sources.lock.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    for row in rows:
        directory = RAW / row["directory"]
        revision = row["commit"]
        if not (directory / ".git").is_dir():
            if args.verify_only:
                raise FileNotFoundError(directory)
            directory.mkdir(parents=True, exist_ok=True)
            if any(directory.iterdir()):
                raise RuntimeError(f"Refusing to initialise a nonempty source directory: {directory}")
            url = "https://github.com/" + row["repository"]
            if row["history"] == "full":
                subprocess.run(["git", "clone", "-q", "--no-checkout", "-c", "core.autocrlf=false", url, str(directory)], check=True)
                subprocess.run(["git", "-C", str(directory), "checkout", "-q", revision], check=True)
            else:
                git("init", "-q", directory)
                git("-C", directory, "config", "core.autocrlf", "false")
                git("-C", directory, "fetch", "-q", "--depth", "1", url, revision)
                git("-C", directory, "checkout", "-q", "--detach", "FETCH_HEAD")
        actual = git("-C", directory, "rev-parse", "HEAD")
        if actual != revision:
            raise RuntimeError(f"{directory}: expected {revision}, found {actual}; preserve local work before checking out the locked revision")
        if git("-C", directory, "diff", "--name-only", "HEAD"):
            raise RuntimeError(f"Modified tracked source files: {directory}")
        print(f"verified {row['repository']} {actual}", flush=True)
    aggregate = RAW / "webshell/Cyc1e183__PHP-Webshell-Dataset"
    extracted = aggregate / "extracted"
    if not args.verify_only and not extracted.exists():
        with zipfile.ZipFile(aggregate / "PHP-Webshell.zip") as archive:
            if sum(i.file_size for i in archive.infolist()) > 1_000_000_000:
                raise RuntimeError("unexpectedly large aggregate archive")
            for entry in archive.infolist():
                if not (extracted / entry.filename).resolve().is_relative_to(extracted.resolve()):
                    raise RuntimeError("archive member escapes the extraction directory")
            archive.extractall(extracted)
    if not extracted.is_dir():
        raise FileNotFoundError(f"Missing extracted aggregate: {extracted}")
    if not args.verify_only:
        (ROOT / "samples/source_revisions.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
