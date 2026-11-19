"""Regression checks for defects that changed research inputs or conclusions."""
import json
import hashlib
import io
import sys
import tempfile
import subprocess
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import analyze
import build_manifest
import fetch_sources
from check_evaluation import check_prediction
from clustering import N_PERM, near_dup_clusters


class ClusteringRegression(unittest.TestCase):
    def test_similar_pair_does_not_need_to_match_bucket_anchor(self):
        sets = [frozenset({99}), frozenset(range(10)), frozenset(range(9))]
        cl, _ = near_dup_clusters(["anchor", "b", "c"], sets,
                                  signatures=np.zeros((3, N_PERM), dtype=np.uint64))
        self.assertNotEqual(cl[0], cl[1])
        self.assertEqual(cl[1], cl[2])

    def test_whitespace_merge_preserves_transitive_near_duplicate_component(self):
        sets = [frozenset({99}), frozenset(range(10)), frozenset(range(9))]
        cl, _ = near_dup_clusters(["c", "a", "b"], sets, ["shared", "shared", "other"],
                                  signatures=np.zeros((3, N_PERM), dtype=np.uint64))
        self.assertEqual(len(set(cl)), 1)

    def test_empty_graphs_are_only_merged_by_whitespace_equivalence(self):
        cl, _ = near_dup_clusters(["a", "b", "c"], [frozenset()] * 3, ["x", "y", "x"])
        self.assertEqual(cl[0], cl[2])
        self.assertNotEqual(cl[0], cl[1])


class ManifestRegression(unittest.TestCase):
    def test_sealed_historical_manifest_cannot_be_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, "Historical v1 inputs are sealed"):
            build_manifest.main()

    def test_token_hash_keeps_whitespace_inside_string_literals(self):
        paths = [ROOT / "tests/construct_cases" / f"literal_{suffix}.php.txt" for suffix in ("a", "b")]
        self.assertEqual(*[build_manifest.ws_norm_hash(p.read_bytes()) for p in paths])
        hashes = build_manifest.token_hashes(paths)
        self.assertNotEqual(hashes[0], hashes[1])

    def test_aggregate_path_is_relative_to_extraction_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "raw"
            aggregate = raw / "webshell/Cyc1e183__PHP-Webshell-Dataset"
            (aggregate / ".git").mkdir(parents=True)
            extracted = aggregate / "extracted"
            extracted.mkdir()
            (extracted / "example.php").write_text("<?php echo strlen('example');")
            out = Path(temporary) / "manifest.csv"
            with patch.multiple(build_manifest, RAW=raw, OUT=out,
                                SOURCES=[("webshell", "webshell/Cyc1e183__PHP-Webshell-Dataset/extracted", "paper", 0)]), \
                 patch.object(build_manifest, "git_first_seen", return_value={"extracted/example.php": "2020-11-13"}):
                build_manifest.main()
            import csv
            with out.open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["relpath"], "example.php")
            self.assertTrue((extracted / row["relpath"]).is_file())
            self.assertEqual(row["first_seen"], "2020-11-13")


class FetchRegression(unittest.TestCase):
    def test_lfs_object_is_downloaded_and_checked_against_its_committed_digest(self):
        data = b"test archive object" * 30
        pointer = ("version https://git-lfs.github.com/spec/v1\n"
                   f"oid sha256:{hashlib.sha256(data).hexdigest()}\nsize {len(data)}")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / "PHP-Webshell.zip"
            archive.write_text(pointer)
            response = io.BytesIO(data)
            response.status = 200
            with patch.object(fetch_sources, "git", return_value=pointer), \
                 patch.object(fetch_sources.urllib.request, "urlopen", return_value=response):
                fetch_sources.materialize_aggregate(directory, "1" * 40)
            self.assertEqual(archive.read_bytes(), data)

    def test_corrupt_lfs_download_does_not_replace_the_pointer(self):
        data = b"test archive object" * 30
        pointer = ("version https://git-lfs.github.com/spec/v1\n"
                   f"oid sha256:{hashlib.sha256(data).hexdigest()}\nsize {len(data)}")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / "PHP-Webshell.zip"
            archive.write_text(pointer)
            response = io.BytesIO(b"x" * len(data))
            response.status = 200
            with patch.object(fetch_sources, "git", return_value=pointer), \
                 patch.object(fetch_sources.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "digest"):
                    fetch_sources.materialize_aggregate(directory, "1" * 40)
            self.assertEqual(archive.read_text(), pointer)

    def test_verify_only_never_downloads_an_unresolved_lfs_object(self):
        data = b"test archive object" * 30
        pointer = ("version https://git-lfs.github.com/spec/v1\n"
                   f"oid sha256:{hashlib.sha256(data).hexdigest()}\nsize {len(data)}")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "PHP-Webshell.zip").write_text(pointer)
            with patch.object(fetch_sources, "git", return_value=pointer), \
                 patch.object(fetch_sources.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
                with self.assertRaisesRegex(RuntimeError, "LFS pointer"):
                    fetch_sources.materialize_aggregate(directory, "1" * 40, verify_only=True)

    def test_existing_checkout_with_wrong_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            repo = raw / "benign/example"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "example.txt").write_text("original content")
            subprocess.run(["git", "-C", str(repo), "add", "example.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
            (root / "sources.lock.tsv").write_text("directory\trepository\tcommit\thistory\tlicense\n"
                + "benign/example\texample/repo\t" + "0" * 40 + "\tshallow\tCC0\n")
            with patch.multiple(fetch_sources, ROOT=root, RAW=raw), \
                 patch.object(sys, "argv", ["fetch_sources.py", "--verify-only"]):
                with self.assertRaisesRegex(RuntimeError, "expected"):
                    fetch_sources.main()


class AnalysisRegression(unittest.TestCase):
    def test_novel_webshell_recall_uses_the_eighteen_cross_source_ids(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(analyze, "TAB", Path(temporary)):
            summary = defaultdict(dict)
            analyze.hard_benign(summary)
        gat = summary["hard_benign"]["results"]["GAT"]
        self.assertAlmostEqual(gat["base"]["18 novel webshells: recall"][0], 0.6444444444444444)
        self.assertAlmostEqual(gat["aug"]["18 novel webshells: recall"][0], 0.5444444444444444)
        self.assertAlmostEqual(gat["base"]["all benign files: FPR"][0], 0.025169273873453187, places=5)


class EvidenceRegression(unittest.TestCase):
    def prediction(self):
        from common import metrics
        probabilities = [.4999996, .7, .1, .8]
        labels = [0, 1, 0, 1]
        sha = ["a", "b", "c", "d"]
        result = dict(test=metrics(labels, np.array(probabilities) >= .5),
                      pred=dict(sha=sha, y=labels, p=probabilities))
        return result, dict(test=sha), dict(zip(sha, ("benign", "webshell", "benign", "webshell")))

    def test_full_precision_probabilities_reproduce_threshold_counts(self):
        result, split, labels = self.prediction()
        check_prediction(result, split, labels, "near-threshold test")

    def test_rounded_threshold_probability_is_rejected_if_it_changes_confusion_counts(self):
        result, split, labels = self.prediction()
        result["pred"]["p"][0] = .5
        with self.assertRaisesRegex(ValueError, "confusion matrix"):
            check_prediction(result, split, labels, "rounded test")


if __name__ == "__main__":
    unittest.main()
