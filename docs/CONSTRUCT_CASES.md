# PHP-Construct-22

This original CC0 artifact contains 22 benign snippets (11 pairs) for inspecting the PHP graph extractor.
Source, labels, rationale, pair membership, split and limits are in `tests/construct_cases/manifest.json`.
All fixtures use the `analysis_only` split and are excluded from classifier training, validation and testing.
They contain no webshell or attacker-controlled command execution. Input files are stored as `.php.txt` and
are **parsed, never executed**. Their purpose is to expose representation limitations, not estimate detection quality.

Run `python3 src/construct_cases.py` with PHP CLI and the pinned tools from `scripts/setup_tools.sh`.
The checked observations use PHP 8.2.35, PHP-Parser commit `715f4d25e225bc47b293a8b997fe6ce99bf987d2`
and LChecker `c8a3646872a937024c3dd3f1dbe346832f55ef62`, in a container with no external network.

Outputs in `results/construct_cases/` include source SHA-256, exact raw/normalised nodes, risk levels,
edges, pruning statistics and DOT diagrams. `summary.json` records the extractor hash and runtime.
The script also generates `results/tables/construct_cases.tex` for the extended report.

| Construct | Observation | Implication |
|---|---|---|
| Data dependency | Output from an input-derived variable and from a fixed variable can share the same normalised graph | Control-flow edges and collapsed variable names cannot establish taint flow |
| Escaping | `htmlspecialchars` remains in node text; risk stays 0 | Text features do not prove sanitisation |
| Dynamic call | A concatenated function name remains unresolved | No constant propagation or dynamic target recovery |
| Callback | Fixed benign `strlen` callback receives risk 1 | Callback capability is not malicious intent |
| Namespace | Plain and namespaced forms have identical graphs | Framework coverage improves but name context is lost |
| Exceptions | Try/catch/finally becomes the same graph as sequential code | Alternative exception paths are lost |
| Local names | Renaming variables preserves the normalised graph | Invariance also erases variable identity |
| String whitespace | Old byte-level hash collides for different string literals | V2 removes lexical whitespace only, preserving strings/comments |
| PHP syntax | Closure: 3 nodes/3 edges; arrow function: 2 nodes/1 edge | Parsing support is broader than faithful CFG lowering |
| Dangerous API | Both fixed commands with safe argument handling receive risk 2 | Risk does not encode argument safety or authorisation |
| Encoding | Plain constant output is pruned; decoded constant output is retained with risk 0 | Encoded data is not decoded into a program |

The annotated data-dependency graph and full table are in `report/sections/constructs.tex`.
This study deliberately reports extractor observations without classifier probabilities. An unchanged graph is
evidence of representation loss only; it does not prove two PHP programs have the same semantics.

## Complementary corpus error inspection

The extended report also inspects three purposively selected seed-0 GAT errors from the main corpus.
These are separate from PHP-Construct-22 and do not add independent human labels. Source labels remain unchanged.
`report/generated/corpus_case_review.json` records source hashes, measured scores, numeric graph observations,
the extractor hash and the inspection runtime; it contains no raw corpus code.

| SHA-256 prefix | Static observation | Interpretation limit |
|---|---|---|
| `068cde77e351` | Large legacy shell/administration text; 24 parser diagnostics, no AST and no graph nodes | Raw API-looking text is lost at parsing; successful execution is not established |
| `c9b3fa1dada1` | A 28-byte Laravel malformed-error-view fixture becomes one unresolved risk-0 call node and is flagged | A high score can occur without a risk-list match; no causal feature attribution is claimed |
| `4fd9cb8f4b32` | MySQL helper wrapper; 45 nodes, 62 edges, no listed risky API or direct request-read token; scored benign under a collection webshell label | Supporting code and intended use cannot be adjudicated from collection membership or a wrapper alone |

Only source reading and parsing were used. The original 300 independent audit decisions remain unfilled.
