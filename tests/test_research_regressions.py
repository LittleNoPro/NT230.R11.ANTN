"""Regression checks for defects that changed research inputs or conclusions."""
import json
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


if __name__ == "__main__":
    unittest.main()
