# Data card — GlareShell-R

GlareShell-R rebuilds the static PHP benchmark described by Feng et al., Computer Networks 245 (2024),
DOI 10.1016/j.comnet.2024.110406. The paper's original corpus was unavailable. We measure duplicate overlap,
source confounds, syntax failures and confusion with legitimate PHP capabilities.

## Version status

The v2 evaluation is complete: 346 runs and 40 splits passed validation. Checked public evidence is in evaluation/v2/; private graphs, caches and models remain in reproductions/v2/.
Root `data/` and `results/` retain v1 inputs/predictions, sealed in `results/provenance.json`. V1's byte whitespace
hash merged different literals and its LSH implementation missed candidate comparisons. V1 predictions are not
results of the corrected algorithm.

All 24 upstream repositories are fixed at full commits in `sources.lock.tsv`. Complete verified sources are
available in this workspace and on the authorized GPU machine. Verification checks HEAD, tracked modifications,
the aggregate LFS object's committed size/SHA-256, and every extracted member. Unresolved LFS pointers are rejected.

## Composition

Counts come from the v2 manifest. Representatives prefer paper sources, then fixed priority. Lexical deduplication
ignores only PHP `T_WHITESPACE`, preserving strings, comments and inline HTML.

| Label / subset | Repository @ commit | Candidates | PHP tag | Exact | Lexical | License |
|---|---|---:|---:|---:|---:|---|
| benign / heldout | joomla/joomla-cms @a5e3be9a4e | 3,105 | 3,105 | 3,104 | 3,104 | GPL-2.0-or-later |
| benign / heldout | laravel/framework @7e0701bf59 | 2,193 | 2,100 | 2,100 | 2,100 | MIT |
| benign / heldout | matomo-org/matomo @7b5e5f9bb6 | 3,085 | 3,071 | 2,946 | 2,946 | GPL-3.0-or-later |
| benign / heldout | phpmyadmin/phpmyadmin @11e127f3fa | 951 | 951 | 951 | 951 | GPL-2.0-or-later |
| benign / paper | PHPMailer/PHPMailer @039de174cd | 124 | 124 | 123 | 123 | LGPL-2.1 |
| benign / paper | WordPress/WordPress @d86d26bd27 | 1,452 | 1,452 | 1,448 | 1,448 | GPL-2.0-or-later |
| benign / paper | doorgets/CMS @f6b53642b9 | 1,573 | 1,568 | 1,449 | 1,445 | unspecified |
| benign / paper | drupal/drupal @d4c491f770 | 9,868 | 9,866 | 9,860 | 9,860 | GPL-2.0-or-later |
| benign / paper | laravel/laravel @d3287461e1 | 51 | 50 | 50 | 50 | MIT |
| webshell / heldout | BlackArch/webshells @e8e1a379c3 | 201 | 186 | 15 | 14 | unspecified |
| webshell / heldout | xl7dev/WebShell @f7cd87feb5 | 282 | 278 | 31 | 28 | GPL-2.0 |
| webshell / paper | Cyc1e183/PHP-Webshell-Dataset @59ff14ffb0 | 2,917 | 2,908 | 2,908 | 2,829 | unspecified |
| webshell / paper | JohnTroony/php-webshells @226a15d068 | 119 | 110 | 27 | 27 | unspecified |
| webshell / paper | bartblaze/PHP-backdoors @8ca75ed86a | 184 | 181 | 33 | 33 | CC0-1.0 |
| webshell / paper | tennc/webshell @6b17eae4a0 | 381 | 378 | 129 | 127 | MIT |

There are **26,486 candidate paths** and **25,174 exact representatives**: paper 3,097 webshells / 12,930 benign;
held-out 46 webshells / 9,101 benign. Paths without a PHP tag and conflicting-label groups are excluded; 27 candidate
rows carry a lexical-hash label conflict. Paper benign subsampling uses proportional largest remainders and seed
2024 to retain exactly **10,375** files, correcting v1's total of 10,376. Similar counts do not imply the same corpus.

## Labels and provenance

Collections supply `webshell`; applications supply `benign`. These proxy labels do not establish intent,
authorization or current exploitability. Kits include helpers; applications include suspicious test fixtures and
legitimate administration code. No file is silently relabelled after its prediction. See [LABEL_GUIDE.md](LABEL_GUIDE.md).

The aggregate has 2,917 candidates. MD5 matching attributes 646; 2,271 have unknown origin. Fixed matching priority
is not proof of earliest publication, authorship or family. Git dates are upload dates, not infection dates; shallow
sources lack history. No temporal generalisation is claimed.

The historical audit has **150 restored blinded copies and 300 unfilled human decisions**. Sheets and key are
unchanged. No agreement or label-error rate is claimed. It remains a v1 audit, not a representative v2 audit.
See [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md).

## Representation and duplicate control

PHP 8.2.35, PHP-Parser 4.19.4 and pinned LChecker produce graphs capped at 2,000 nodes. Paper webshells include
139 recovered parse errors, 53 empty graphs and 477 truncated graphs. Four extraction attempts fail, including
missing records after isolated retries. Failures remain as empty graphs rather than being removed.

V2 clusters normalized-statement sets using 128-permutation, 32-band MinHash-LSH, exact Jaccard >= 0.8 verification
of every eligible bucket pair, and one union-find for lexical hashes and identical nonempty sets. Empty graphs
merge only by lexical hash. There is no large-bucket skip. LSH still misses some pairs; transitive components need
not have every pair above 0.8. They are representation clusters, not verified malware families.
The 3,097 paper webshells form **1,395 clusters** (445 singletons, largest 55); no cluster mixes labels in this run.

## Splits and selection

Main comparisons use five seeds; sweeps use seeds 0–2.

- `paper_random`: exact dedup; 3,097 webshells / 10,375 benign; stratified 8:1:1. Recorded webshell test-to-train
  cluster overlap is 71.9–83.2% over seeds, rather than an exhaustive leakage estimate.
- `clean_group`: lexical dedup then whole-cluster partitions towards 8:1:1; 3,016 webshells / 10,372 benign.
  Main-corpus clusters are disjoint between train, validation and test.
- `cross_source`: clean training/validation; **20 novel webshells and 9,092 benign files** from four unseen projects.
  Test components are absent from all paper sources. Twenty positives give a coarse recall estimate.
- `loo_tennc`, `loo_bartblaze`, `loo_xl7dev`: attribution holdouts with 365, 178 and 139 test webshells. Components
  touching test positives are removed from training/validation; clean benign partitions are reused. This is not a
  verified family split.
- `base`, `aug`: matched auxiliary experiments. Test IDs match within each seed; clean membership varies between seeds.

Embeddings, TF-IDF and feature selection are fitted only on training files. Checkpoint selection uses validation
F1; classification uses threshold 0.5. Alarm-budget thresholds use the test ROC and are labeled **optimistic oracle
bounds**, not calibrated deployment performance. Seed intervals do not cover arbitrary future projects.

## Auxiliary benign applications

Training: YOURLS, FluxBB, DokuWiki, Cacti, Adminer, capped at 1,000 retained files per project. Test: OPNsense core,
osTicket, MyBB, Tiny File Manager. Main-corpus and within-track exact/token duplicates are removed. Added files
are **not** main-corpus near-duplicate clustered, a narrower leakage control than `clean_group`. Training-project
files are split between train/validation; test projects remain unseen. Twelve original benign standalone probes
provide a stress test, not a representative server sample.

License files at locked revisions: YOURLS — MIT; FluxBB, DokuWiki, Cacti, osTicket — GPL v2 texts; MyBB — LGPL v3;
OPNsense core — BSD two-clause text; Tiny File Manager — GPL v3; Adminer — Apache 2.0 or GPL 2.0. Bundled code can
carry additional notices; consult the pinned files. No new license is imposed on upstream source.

## Original optional artifact

[PHP-Construct-22](CONSTRUCT_CASES.md) supplies 22 original benign snippets in 11 pairs, with CC0 license, hashes,
label rationales and `analysis_only` split in `tests/construct_cases/manifest.json`. They are excluded from all
classifier partitions. Exact emitted graphs and DOT files are in `results/construct_cases/`. An all-benign
extractor artifact cannot estimate detection accuracy or replace human label review.

## Limits

- Framework benign code and procedural PHP 4/5-era webshells differ in syntax, size, age and parseability. These can
  be shortcuts. The structural/risk-statistics baseline includes API/input indicators, not pure topology alone.
- The unit is a source file, not a request, infection or industrial server. There is no runtime taint proof,
  dynamic include recovery, general deobfuscation or industrial deployment evaluation.
- Selection includes `.php`, `.php3`–`.php7`, `.phtml`, `.inc`; other framework suffixes, disguised extensions,
  memory-resident payloads and non-PHP shells are outside the corpus.
- Text baselines read at most 100,000 bytes and use hashed 1–2-grams. Graph text is truncated and normalized;
  pruning, undirected model edges and flattened exceptions lose information.
- Corpus priors differ from rare-webshell deployment. Public variants are correlated; projects are few. Precision
  cannot transfer unchanged to a live server. Human label verification remains pending.

## Distribution

Samples are parsed/read as bytes, never executed, included as PHP, served or deployed. The evaluation container
has no external network and read-only samples. Raw code, graph fragments, caches and weights are Git-ignored.
Public evidence contains hashes, paths, labels, numeric statistics and predictions.

For a private grading archive, `scripts/pack_samples.sh` accepts `GLARESHELL_DATA` and `GLARESHELL_SAMPLE_ARCHIVE`,
includes selected main/auxiliary files, uses password `infected` and writes a SHA-256 checksum. Keep it private.
Fetching depends on upstream availability; verified local copies preserve the current locked corpus.
