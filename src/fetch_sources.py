"""Fetch exact upstream revisions from sources.lock.tsv; never execute samples."""
import argparse
import csv
import json
import hashlib
import time
import subprocess
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "samples/raw"


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


def materialize_aggregate(directory, revision, verify_only=False):
    """Verify the Git LFS object against its committed pointer, without git-lfs."""
    name = "PHP-Webshell.zip"
    pointer = git("-C", directory, "show", f"{revision}:{name}")
    if not pointer.startswith("version https://git-lfs.github.com/spec/v1\n"):
        raise RuntimeError("Unexpected aggregate format: expected a committed Git LFS pointer")
    fields = dict(line.split(" ", 1) for line in pointer.splitlines()[1:])
    expected = fields["oid"].removeprefix("sha256:")
    size = int(fields["size"])
    if len(expected) != 64 or not 0 < size <= 1_000_000_000:
        raise RuntimeError("Invalid aggregate LFS metadata")
    archive = directory / name
    if archive.stat().st_size != size:
        if verify_only:
            raise RuntimeError("Aggregate is still an LFS pointer; run scripts/fetch_sources.sh with network access")
        url = ("https://media.githubusercontent.com/media/Cyc1e183/PHP-Webshell-Dataset/"
               + revision + "/" + urllib.parse.quote(name))
        temporary = archive.with_suffix(".zip.download")
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset > size:
            temporary.unlink()
            offset = 0
        if offset == size:
            with temporary.open("rb") as stream:
                complete = hashlib.file_digest(stream, "sha256").hexdigest() == expected
            if complete:
                temporary.replace(archive)
                return
            temporary.unlink()
            offset = 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request, timeout=120) as response:
            resumed = offset > 0 and response.status == 206
            total = offset if resumed else 0
            with temporary.open("ab" if resumed else "wb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > size:
                        raise RuntimeError("Aggregate exceeds its committed LFS size")
                    output.write(chunk)
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if total != size or digest != expected:
            if total == size:
                temporary.unlink()  # do not retain a corrupt completed object
            raise RuntimeError("Downloaded aggregate differs from committed LFS size/digest")
        temporary.replace(archive)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError("Aggregate archive fails its committed LFS SHA-256")


def fetch_one(row, verify_only=False):
    directory = RAW / row["directory"]
    revision = row["commit"]
    initialized = (directory / ".git").is_dir()
    has_head = initialized and subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not has_head:
        if verify_only:
            raise FileNotFoundError(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if any(p.name != ".git" for p in directory.iterdir()):
            raise RuntimeError(f"Refusing to initialise a nonempty source directory: {directory}")
        url = "https://github.com/" + row["repository"]
        if not initialized:
            git("init", "-q", directory)
        git("-C", directory, "config", "core.autocrlf", "false")
        depth = ["--depth", "1"] if row["history"] == "shallow" else []
        # Fetch the locked commit and its ancestors, excluding future branch history.
        git("-C", directory, "fetch", "-q", *depth, url, revision)
        git("-C", directory, "checkout", "-q", "--detach", "FETCH_HEAD")
    actual = git("-C", directory, "rev-parse", "HEAD")
    if actual != revision:
        raise RuntimeError(f"{directory}: expected {revision}, found {actual}; preserve local work before checking out the locked revision")
    aggregate_repo = row["repository"] == "Cyc1e183/PHP-Webshell-Dataset"
    if aggregate_repo:
        materialize_aggregate(directory, revision, verify_only)
    paths = ["--", ".", ":(exclude)PHP-Webshell.zip"] if aggregate_repo else []
    if git("-C", directory, "diff", "--name-only", "HEAD", *paths):
        raise RuntimeError(f"Modified tracked source files: {directory}")
    print(f"verified {row['repository']} {actual}", flush=True)


def fetch_with_retries(row, verify_only=False):
    for attempt in range(5):
        try:
            return fetch_one(row, verify_only)
        except (OSError, subprocess.CalledProcessError) as error:
            if verify_only or attempt == 4:
                raise
            print(f"retry {attempt + 1}/4: {row['repository']}: {type(error).__name__}", flush=True)
            time.sleep(min(30, 2 ** (attempt + 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true", help="check checkouts against the lock without network access")
    ap.add_argument("--workers", type=int, default=4, help="independent source downloads (default: 4)")
    args = ap.parse_args()
    with (ROOT / "sources.lock.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if args.workers < 1:
        ap.error("--workers must be positive")
    with ThreadPoolExecutor(args.workers) as executor:
        list(executor.map(lambda row: fetch_with_retries(row, args.verify_only), rows))
    aggregate = RAW / "webshell/Cyc1e183__PHP-Webshell-Dataset"
    extracted = aggregate / "extracted"
    with zipfile.ZipFile(aggregate / "PHP-Webshell.zip") as archive:
        if sum(i.file_size for i in archive.infolist()) > 1_000_000_000:
            raise RuntimeError("unexpectedly large aggregate archive")
        for entry in archive.infolist():
            destination = extracted / entry.filename
            if not destination.resolve().is_relative_to(extracted.resolve()):
                raise RuntimeError("archive member escapes the extraction directory")
            if entry.is_dir():
                continue
            payload = archive.read(entry)  # checks the ZIP member CRC without interpreting PHP
            expected = hashlib.sha256(payload).hexdigest()
            if destination.is_file():
                with destination.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                        continue
            if args.verify_only:
                raise RuntimeError(f"Missing or changed extracted archive member: {entry.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    if not extracted.is_dir():
        raise FileNotFoundError(f"Missing extracted aggregate: {extracted}")
    if not args.verify_only:
        (ROOT / "samples/source_revisions.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
