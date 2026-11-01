# Manual label audit protocol

Goal: estimate how often the source-level labels (`webshell` = "file from a public collection",
`benign` = "file from a framework release") are wrong, and how many of GAT's errors are really label errors.

## What was prepared (`python src/label_audit.py sample`)
* 150 files, sampled with a fixed seed from five strata:

  | Stratum | n | Pool |
  |---|---|---|
  | GAT false negatives (webshells GAT misses, mean p < 0.5 over clean_group + cross_source seeds) | 25 | 41 |
  | GAT false positives (benign files GAT flags) | 25 | 117 |
  | Risky benign (benign with at least one critical call) | 25 | 58 |
  | Random webshells | 50 | 3,143 |
  | Random benign | 25 | 22,031 |

* Each file is copied, under a random id, to `samples/audit/A###.txt`. The `.txt` extension and the location
  outside the web root mean the copy is never interpreted as PHP. `samples/` is not in git.
* Each auditor has a sheet `data/audit/sheet_<name>.csv` with 100 files. Every file is reviewed by exactly two of
  the three auditors (pairs rotate: Tu–Vu, Vu–Duc, Duc–Tu).
* **Blinding:** the sheets show only the id. **Do not open `data/audit/audit_key.csv`** (it holds the current label,
  the source and the stratum) until all three sheets are complete.

## Safety
* Open the files only in a text editor or viewer (VS Code, `less`) inside the analysis VM. Never `php` them,
  never copy them into a web root, never rename them to `.php`.
* Some files contain encoded payloads. Do not decode and run them. Read the code statically.

## How to judge one file
Use the definitions in `docs/LABEL_GUIDE.md`. Ask: *if this file appeared on a production web server, would it give
a remote party control the site owner did not intend?*

| Column | Values |
|---|---|
| `verdict` | `webshell`, `benign` or `unsure` (lower case) |
| `case` | optional, the confusable-case number from the label guide: `1` benign with risky capability, `2` webshell without dangerous built-ins, `3` payload hidden in data, `4` fragment/helper from a kit, `5` variant; or `clear` |
| `notes` | one short phrase, e.g. "phpinfo only", "c99 variant", "installer step", "CSS emitter from kit" |

Rules:
* A helper shipped inside a webshell kit that does nothing malicious on its own (config, CSS/JS emitter,
  `phpinfo()`, a database class) is `benign`, case `4`.
* An obfuscated blob whose decoded content you cannot see statically, wrapped in `eval`, is `webshell`, case `3`.
* A legitimate admin feature (backup, installer, file manager inside a CMS) protected by the application's own
  authentication is `benign`, case `1`.
* Use `unsure` only when you cannot decide after reading it. Do not guess.
* Expect 1–2 minutes per file, so about 2–3 hours per auditor. Work independently and do not discuss files until all
  sheets are filled.

## After all three sheets are filled
```bash
cd src && python label_audit.py score
```
This checks that every row has a valid verdict and writes:
* `data/audit/audit_result.csv`: final audit label per file (agreement, otherwise `disagree`).
* `results/label_audit.json`: Cohen's κ per auditor pair and the per-stratum label-error rate with Wilson 95% CIs.
* `results/tables/label_audit.tex`: the table for the report.

Disagreements: meet, discuss each `disagree` file, and write the agreed verdict to `data/audit/adjudication.csv`
(columns `audit_id,verdict`). Then run `score` again.
