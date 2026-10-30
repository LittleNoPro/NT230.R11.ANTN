# Data card — GlareShell-R (PHP webshell / benign script corpus with near-duplicate control)

## 1. Motivation
GlareShell (Feng et al., *Computer Networks* 245, 2024) reports F1 = 0.9887 on a self-collected corpus
(3,104 webshells / 10,375 benign files) split **randomly** 8:1:1 after **exact-hash** deduplication.
The corpus itself is not released. GlareShell-R rebuilds the corpus from the sources listed in the
paper's Table 1, documents its provenance, and adds what is needed to measure — and control — leakage and
source bias:

* a second, stricter deduplication level (whitespace-insensitive hash);
* near-duplicate clusters over normalised ICFG statements (MinHash-LSH, verified Jaccard ≥ 0.8);
* a **cluster-disjoint** split (`clean_group`) and a **cross-source** test set of projects/collections that
  are absent from the paper's sources (`cross_source`).

Scale is deliberately moderate (≈25k files); the contribution is in labelling hygiene, not volume.

## 2. Composition (files ending in .php/.phtml/.php3-7/.inc)

| Label | Subset | Source (pinned commit/tag) | License | Files | contain `<?` | exact-dedup | ws-dedup |
|---|---|---|---|---|---|---|---|
| webshell | paper | Cyc1e183/PHP-Webshell-Dataset @59ff14f (aggregate of 17 collections incl. the deleted ysrc/webshell-sample) | none stated | 2917 | 2908 | 2917 | 1652 |
| webshell | paper | bartblaze/PHP-backdoors @8ca75ed | CC0-1.0 | 184 | 181 | — | — |
| webshell | paper | tennc/webshell @6b17eae (PHP part) | MIT | 381 | 378 | — | — |
| webshell | paper | JohnTroony/php-webshells @226a15d | none stated | 119 | 110 | — | — |
| webshell | heldout | BlackArch/webshells @e8e1a37 (PHP part) | none stated | 201 | 186 | — | — |
| webshell | heldout | xl7dev/WebShell @f7cd87f (PHP part) | GPL-2.0 | 282 | 278 | — | — |
| benign | paper | WordPress 6.4.3, drupal 10.2.5, laravel/laravel v10.3.3, PHPMailer v6.9.1, doorgets/CMS @f6b5364 | GPL-2.0+/GPL-2.0+/MIT/LGPL-2.1/none stated | 13068 | — | 12930 | 12924 |
| benign | heldout | laravel/framework v10.48.4, phpMyAdmin 5.2.1, Joomla 5.0.3, Matomo 5.0.3 | MIT/GPL-2.0/GPL-2.0+/GPL-3.0 | 9334 | — | 9101 | 9100 |

The per-source dedup funnel is generated in `results/tables/dataset_funnel.tex`.
After exact dedup the paper subset holds **3,097 webshells** (paper: 3,104) and 12,930 benign files, which
we subsample to the paper's **10,375** (proportionally per project, seed 2024).

## 3. Collection & cleaning
`scripts/fetch_sources.sh` clones every source at the pinned revision; `src/build_manifest.py` records for
every file: SHA-256, MD5, whitespace-normalised hash, size, source repo, relative path, first-seen git date
(only for non-shallow webshell clones), whether it contains a PHP open tag, and two dedup flags.
* `keep_exact` — first copy per SHA-256 (paper subset preferred, then source priority);
* `keep_ws` — first copy per whitespace-normalised hash;
* files whose copies carry **both labels** are dropped (30 files, e.g. benign libraries bundled in webshell kits);
* files without `<?` are dropped (not PHP code: templates, renamed text).

Provenance inside the Cyc1e183 aggregate is recovered by MD5 matching against the individual
collections: 2,271 of its 2,917 files match none of the collections we could clone (origin = `unknown`).

## 4. Labels
See `docs/LABEL_GUIDE.md`. Labels are **source-level** (collection ⇒ webshell, release tarball of a vetted
project ⇒ benign); no file was relabelled by hand. Known consequences: webshell collections contain
helper files and non-malicious fragments (e.g. a CSS-only page, `phpinfo()` probes), and benign projects
contain test fixtures that *look* malicious. These are counted in the error analysis, not removed, to avoid
cherry-picking.

## 5. Near-duplicate structure (main finding)
* 1,265 of the 2,917 Cyc1e183 files (43%) are byte-identical once whitespace is ignored.
* The 3,097 paper-subset webshells form only **1,368 near-duplicate clusters**.
* Under the paper's random 8:1:1 protocol, **73–81% of test webshells** (5 seeds) have a near-duplicate in
  the training set (benign: 8–11%).
* `clean_group` keeps whole clusters on one side: 1,747 webshells / 10,372 benign, 8:1:1 by cluster.
* `cross_source` test = 9,091 held-out benign files + 18 webshells that are not near-duplicates of anything
  in the paper subset. 18 is small — recall on it is reported with Wilson intervals, the set is mainly a
  false-positive stress test.

## 6. Splits & schema
`data/splits/{paper_random,clean_group,cross_source}_s{0..4}.json` → `{"train": [sha256...], "val": [...], "test": [...]}`.
Schema of every CSV: `docs/SCHEMA.md`.

## 7. Known biases & limitations
* **Source confound**: benign = 5 large frameworks/CMS (class-based, namespaced, PSR style); webshells =
  standalone procedural scripts. A model can separate "framework file vs. standalone script" without learning
  maliciousness — see the graph-statistics baseline in the report.
* **Era confound**: many webshells are PHP 4/5 era (short tags, `mysql_*`), benign releases are 2023–2024.
* No temporal split: the Cyc1e183 aggregate has no timestamps and the original collections have
  shallow/merged histories; we use source-disjointness instead.
* Benign projects are subsampled, so the class prior (23% webshell) is far from deployment reality
  (webshells are rare): precision in deployment would be lower than any number reported here.

## 8. Safety & distribution
Webshells are **never executed**: the pipeline only parses them (PHP-Parser) and reads bytes. Raw files live in
`samples/` (git-ignored). The repository ships only hashes, paths and scripts to re-fetch from the original public
sources. For grading, `scripts/pack_samples.sh` builds a password-protected zip (`infected`) with a SHA-256
checksum, to be handed over privately, never uploaded publicly.

## 9. Maintenance
Pinned revisions make the corpus re-buildable as long as the upstream repositories exist (ysrc/webshell-sample
already disappeared; its files survive only inside the Cyc1e183 aggregate).
