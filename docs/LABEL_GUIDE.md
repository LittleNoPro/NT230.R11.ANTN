# Label guide

| Label | Definition | Assigned when |
|---|---|---|
| `webshell` (1) | A server-side PHP script whose purpose is to give a remote party unauthorised control over the web server: run OS commands, evaluate attacker-supplied PHP, browse/upload/modify files, access databases, or open a reverse/bind shell. Includes one-line backdoors (`eval($_POST[x])`), obfuscated loaders and full "management" kits (c99, r57, b374k, WSO). | The file comes from a public webshell collection listed in the data card and survives deduplication with a consistent label. |
| `benign` (0) | A PHP script from a widely deployed, maintained open-source project release. | The file comes from a pinned release of a benign project listed in the data card. |
| dropped | Same content (whitespace-insensitive) appears under both labels, or the file has no PHP open tag. | Automatic (`label_conflict`, `is_php`). |

## Threat model the labels encode
* **Attacker**: has already exploited a vulnerability (upload, LFI/RFI, injection, stolen credentials) and drops a
  PHP file into the web root of a web server (in the paper's setting: the management server of an Industrial
  Internet deployment).
* **Goal**: persistent remote command execution / data exfiltration / pivoting.
* **Observation surface**: the *source file* on disk when it is created or modified (file-system monitor);
  no runtime behaviour, no HTTP traffic. Detection is purely static.
* **Out of scope**: in-memory webshells, webshells in other languages, legitimate admin tools deployed on
  purpose (e.g. phpMyAdmin) — these are exactly the "benign file with risky capability" case and are labelled benign.

## Confusable cases (reviewed in the error analysis)
1. **Benign code with webshell capabilities** — installers, updaters, backup tools, image libraries calling
   `exec()`/`proc_open()`; frameworks using `call_user_func_array` everywhere (dispatch, events, DI).
2. **Webshells without dangerous built-ins** — uploaders / file managers using only `move_uploaded_file`,
   `fopen/fwrite`; database managers; obfuscated shells that build the function name at run time (`$f = 'sys'.'tem'; $f($_GET[c]);`).
3. **Payload hidden in data** — `eval(gzinflate(base64_decode('...')))`: the static ICFG contains one statement
   and an opaque string.
4. **Fragments / helpers** shipped inside webshell kits (CSS/JS emitters, configs).
5. **Variants of the same family** (same kit, different banner/password) — handled by near-duplicate clustering,
   not by relabelling.
