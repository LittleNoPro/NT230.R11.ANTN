<?php
/**
 * GlareShell reproduction — ICFG extractor (paper §3.1 + §3.2 preprocessing).
 *
 * Reuses LChecker's intra-procedural CFG builder (tools/LChecker/src/ConstructCFG.php,
 * as the paper does) and adds what the paper describes on top of it:
 *   - Algorithm 1: connect per-function CFGs through call relations into one ICFG,
 *   - pruning of "meaningless" statements (constant echo / variable initialisation),
 *   - statement normalisation (local / user_define / im),
 *   - risk level per statement (0 normal, 1 obfuscated, 2 critical).
 *
 * STATIC ANALYSIS ONLY: input files are parsed, never included or executed.
 *
 * Usage: php -d short_open_tag=On extract_icfg.php <list.tsv> <out.jsonl>
 *   (short_open_tag must be On: many old webshells use bare "<?" tags)
 *   list.tsv lines: <sample_id>\t<absolute path>
 *
 * Deviations from vanilla LChecker (documented in the report):
 *   (D1) namespace / try-catch / declare blocks are flattened before CFG construction
 *        (LChecker silently drops them, which empties most modern benign files);
 *   (D2) functions/classes declared inside other statements and closures are hoisted;
 *   (D3) functions/methods never called from the main body are kept as extra components.
 */
namespace DeepCopy {
    // LChecker depends on myclabs/deep-copy only for this helper.
    if (!function_exists('DeepCopy\deep_copy')) {
        function deep_copy($x) { return unserialize(serialize($x)); }
    }
}

namespace {

error_reporting(E_ERROR | E_PARSE);
ini_set('memory_limit', '1024M');

use PhpParser\Node;
use PhpParser\Node\Expr;
use PhpParser\Node\Stmt;
use PhpParser\Node\Scalar;
use PhpParser\NodeTraverser;
use PhpParser\NodeVisitorAbstract;
use PhpParser\NodeFinder;
use PhpParser\ParserFactory;
use PhpParser\PrettyPrinter;
use PhpParser\ErrorHandler;

require_once __DIR__ . '/../../tools/LChecker/src/ConstructCFG.php';

const MAX_NODES = 2000;          // cap per ICFG (recorded as `truncated`)
const MAX_STMT_CHARS = 256;      // statement text cap
const MAX_STR_LITERAL = 64;      // string literal cap inside a statement
const FILE_TIMEOUT_S = 20;

$SUPERGLOBALS = ['_GET','_POST','_REQUEST','_COOKIE','_SERVER','_FILES','_ENV','_SESSION','GLOBALS','this',
                 'HTTP_GET_VARS','HTTP_POST_VARS','HTTP_COOKIE_VARS','HTTP_SERVER_VARS','HTTP_POST_FILES','HTTP_RAW_POST_DATA'];
// Risk criteria (paper §3.2.2, following its ref. [32])
$CRITICAL = array_flip(['system','exec','shell_exec','passthru','popen','proc_open','pcntl_exec','expect_popen']);
$OBFUSCATED = array_flip(['eval','assert','preg_replace','preg_replace_callback','preg_filter','mb_ereg_replace',
    'create_function','call_user_func','call_user_func_array','forward_static_call','forward_static_call_array',
    'array_map','array_filter','array_walk','array_walk_recursive','array_reduce','array_udiff','array_uintersect',
    'usort','uasort','uksort','iterator_apply','register_shutdown_function','register_tick_function',
    'set_error_handler','set_exception_handler','ob_start','header_register_callback','spl_autoload_register']);
// PHP built-ins: functions of this interpreter + prefixes of common extensions not loaded here
$INTERNAL = array_flip(get_defined_functions()['internal']);
$EXT_PREFIXES = ['mysql_','mysqli_','mssql_','pg_','sqlite','oci','odbc_','curl_','mb_','image','gd_','exif_','zip_',
    'gz','bz','ldap_','xml','iconv','posix_','pcntl_','openssl_','sodium_','hash','apache_','ob_','session_','mcrypt_',
    'imap_','snmp','ssh2_','ftp_','socket_','stream_','json_','ctype_','intl','grapheme_','gmp_','bc','finfo_','dba_'];

function is_builtin_function(string $name): bool {
    global $INTERNAL, $EXT_PREFIXES;
    $n = strtolower(ltrim($name, '\\'));
    if (isset($INTERNAL[$n])) return true;
    foreach ($EXT_PREFIXES as $p) if (strncmp($n, $p, strlen($p)) === 0) return true;
    return in_array($n, ['eval','assert','exit','die','isset','empty','unset','list','print','echo','include','require'], true);
}

/** (D1)(D2) flatten wrapper blocks so that LChecker sees their statements. */
class Flattener extends NodeVisitorAbstract {
    public function leaveNode(Node $n) {
        if ($n instanceof Stmt\Namespace_ || $n instanceof Stmt\Declare_) return $n->stmts ?? [];
        if ($n instanceof Stmt\TryCatch) {
            $out = $n->stmts;
            foreach ($n->catches as $c) foreach ($c->stmts as $s) $out[] = $s;
            if ($n->finally) foreach ($n->finally->stmts as $s) $out[] = $s;
            return $out;
        }
        if ($n instanceof Stmt\Block) return $n->stmts;   // PHP-Parser >=4.18
        return null;
    }
}

/** Statement normalisation (paper §3.2.1 rules 1-3) applied to a deep copy of the AST node. */
class Normalizer extends NodeVisitorAbstract {
    public function leaveNode(Node $n) {
        global $SUPERGLOBALS;
        if ($n instanceof Expr\Variable && is_string($n->name) && !in_array($n->name, $SUPERGLOBALS, true)) {
            $n->name = 'local'; return $n;                                       // rule 2
        }
        if ($n instanceof Expr\FuncCall && $n->name instanceof Node\Name && !is_builtin_function($n->name->toString())) {
            $n->name = new Node\Name('user_define'); return $n;                  // rule 1
        }
        if (($n instanceof Expr\MethodCall || $n instanceof Expr\StaticCall || $n instanceof Expr\NullsafeMethodCall)
            && $n->name instanceof Node\Identifier) {
            $n->name = new Node\Identifier('user_define'); return $n;            // rule 1 (methods)
        }
        if ($n instanceof Scalar\LNumber || $n instanceof Scalar\DNumber) {
            return new Expr\ConstFetch(new Node\Name('im'));                     // rule 3
        }
        if ($n instanceof Scalar\String_ && strlen($n->value) > MAX_STR_LITERAL) {
            $n->value = substr($n->value, 0, MAX_STR_LITERAL) . '...';
            return $n;
        }
        return null;
    }
}

/** Replace closure / class bodies inside a statement by an empty body (they become their own CFGs). */
class BodyStripper extends NodeVisitorAbstract {
    public function leaveNode(Node $n) {
        if ($n instanceof Expr\Closure || $n instanceof Expr\ArrowFunction) { if (property_exists($n, 'stmts')) $n->stmts = []; return $n; }
        if ($n instanceof Stmt\Class_ && $n->name === null) { $n->stmts = []; return $n; }
        return null;
    }
}

function deep(Node $n) { return unserialize(serialize($n)); }

function print_node($printer, $node): string {
    try {
        if ($node instanceof Stmt) $s = $printer->prettyPrint([$node]);
        else $s = $printer->prettyPrintExpr($node);
    } catch (\Throwable $e) { $s = get_class($node); }
    $s = preg_replace('/\s+/', ' ', $s);
    if (strlen($s) > MAX_STMT_CHARS) $s = substr($s, 0, MAX_STMT_CHARS);
    return $s;   // invalid UTF-8 is substituted at json_encode time
}

function risk_of($node): int {
    global $CRITICAL, $OBFUSCATED;
    $f = new NodeFinder();
    $r = 0;
    foreach ($f->find([$node], function ($x) { return $x instanceof Expr\FuncCall || $x instanceof Expr\ShellExec || $x instanceof Expr\Eval_; }) as $x) {
        if ($x instanceof Expr\ShellExec) return 2;
        if ($x instanceof Expr\Eval_) { $r = max($r, 1); continue; }
        if ($x->name instanceof Node\Name) {
            $nm = strtolower($x->name->toString());
            if (isset($CRITICAL[$nm])) return 2;
            if (isset($OBFUSCATED[$nm])) $r = max($r, 1);
        }
    }
    return $r;
}

/** "Meaningless" statements removed by GlareShell (§3.1): constant output and variable initialisation. */
function is_meaningless($stmt): bool {
    $isConst = function ($e) use (&$isConst) {
        if ($e instanceof Scalar && !($e instanceof Scalar\Encapsed)) return true;
        if ($e instanceof Expr\ConstFetch) return true;
        if ($e instanceof Expr\UnaryMinus) return $isConst($e->expr);
        if ($e instanceof Expr\Array_) { foreach ($e->items as $it) if ($it && !$isConst($it->value)) return false; return true; }
        return false;
    };
    if ($stmt instanceof Stmt\InlineHTML || $stmt instanceof Stmt\Nop) return true;
    if ($stmt instanceof Stmt\Echo_) { foreach ($stmt->exprs as $e) if (!$isConst($e)) return false; return true; }
    if ($stmt instanceof Stmt\Expression && $stmt->expr instanceof Expr\Assign
        && $stmt->expr->var instanceof Expr\Variable && $isConst($stmt->expr->expr)) return true;
    return false;
}

class Graph {
    public $nodes = [];   // id => ['ast'=>Node|null, 'dummy'=>bool]
    public $succ = [];
    public $truncated = false;
    function add($ast, bool $dummy = false): int {
        $id = count($this->nodes);
        $this->nodes[$id] = ['ast' => $ast, 'dummy' => $dummy];
        $this->succ[$id] = [];
        return $id;
    }
    function edge(int $a, int $b) { if ($a !== $b) $this->succ[$a][$b] = true; }
}

/**
 * Lower one LChecker CFG ([Entry, End]) into Graph nodes. Returns [entryId, exitId, stmtNodeIds].
 */
function lower_cfg(Graph $g, $body, array &$stmtNodes): array {
    $entry = $g->add(null, true);
    $prev = $entry;
    $cur = $body[0]->Child ?? null;
    while ($cur !== null && count($g->nodes) < MAX_NODES) {
        if ($cur->Type === Stmt) {
            $id = $g->add($cur->Stmt);
            $stmtNodes[] = $id;
            $g->edge($prev, $id); $prev = $id;
        } elseif ($cur->Type === IfStmt) {
            $join = $g->add(null, true);
            $branchFrom = $prev;
            foreach ($cur->Bodies as $i => $b) {
                $cond = $cur->Conditions[$i] ?? null;
                // LChecker stores a `for` loop's condition list as-is (array of Expr): keep the last one,
                // which is the one PHP actually tests.
                if (is_array($cond)) $cond = count($cond) ? end($cond) : null;
                if ($cond !== null && !($cond instanceof Node)) $cond = null;
                $from = $branchFrom;
                if ($cond !== null) {
                    $cid = $g->add($cond); $stmtNodes[] = $cid;
                    $g->edge($branchFrom, $cid); $from = $cid;
                    $branchFrom = $cid;               // else-if chain hangs off the previous condition
                }
                if ($b === null) { $g->edge($from, $join); continue; }
                [$be, $bx] = lower_cfg($g, $b, $stmtNodes);
                $g->edge($from, $be); $g->edge($bx, $join);
            }
            $g->edge($branchFrom, $join);            // fall-through when no branch is taken
            $prev = $join;
        } elseif ($cur->Type === End) {
            break;
        }
        $cur = $cur->Child;
    }
    if (count($g->nodes) >= MAX_NODES) $g->truncated = true;
    $exit = $g->add(null, true);
    $g->edge($prev, $exit);
    return [$entry, $exit];
}

function extract_file(string $path): array {
    global $nodeindex;
    $nodeindex = 0;
    if (!is_file($path)) throw new \RuntimeException('missing file');
    $code = file_get_contents($path);
    $errors = new ErrorHandler\Collecting();
    $parser = (new ParserFactory)->create(ParserFactory::PREFER_PHP7);
    $stmts = $parser->parse($code, $errors) ?? [];
    $parseErr = $errors->hasErrors();
    $t = new NodeTraverser(); $t->addVisitor(new Flattener());
    $stmts = $t->traverse($stmts);

    // (D2) hoist nested declarations + closures
    $finder = new NodeFinder();
    $funcDecls = $finder->findInstanceOf($stmts, Stmt\Function_::class);
    $classDecls = array_filter($finder->find($stmts, function ($n) { return $n instanceof Stmt\ClassLike && $n->name !== null; }));
    $closures = $finder->find($stmts, function ($n) { return $n instanceof Expr\Closure; });

    // per-function CFGs via LChecker
    $funcs = [];       // key => MyFunction
    $methodsByName = [];
    foreach ($funcDecls as $fd) {
        $f = @ConstructFunctionCFG($fd, MAIN_CLASS);
        $funcs['f:' . strtolower($f->FuncName)] = $f;
    }
    foreach ($classDecls as $cd) {
        $c = @ConstructClassCFG($cd);
        foreach ($c->ClassMethods as $mn => $m) {
            $k = 'm:' . strtolower((string)$cd->name) . '::' . strtolower($mn);
            $funcs[$k] = $m;
            $methodsByName[strtolower($mn)][] = $k;
        }
    }
    foreach ($closures as $i => $cl) {
        $f = new MyFunction(MAIN_CLASS, "{closure}#$i");
        $f->Body = @ConstructCFG($cl->stmts);
        $funcs["c:$i"] = $f;
    }
    $main = @ConstructCFG($stmts);

    // Algorithm 1: lower main CFG, then iteratively resolve call sites and splice callee CFGs
    $g = new Graph();
    $stmtNodes = [];
    [$mEntry, $mExit] = lower_cfg($g, $main, $stmtNodes);
    $lowered = [];     // func key => [entry, exit]
    $queue = $stmtNodes; $qi = 0;
    $closureIdx = new \SplObjectStorage();
    foreach ($closures as $i => $cl) $closureIdx[$cl] = $i;
    $callFinder = function ($ast) use ($finder) {
        return $finder->find([$ast], function ($n) {
            return $n instanceof Expr\FuncCall || $n instanceof Expr\MethodCall || $n instanceof Expr\StaticCall
                || $n instanceof Expr\NullsafeMethodCall || $n instanceof Expr\New_ || $n instanceof Expr\Closure;
        });
    };
    $resolve = function ($call) use (&$funcs, &$methodsByName, $closureIdx) {
        if ($call instanceof Expr\Closure) return isset($closureIdx[$call]) ? ["c:" . $closureIdx[$call]] : [];
        if ($call instanceof Expr\FuncCall && $call->name instanceof Node\Name) {
            $k = 'f:' . strtolower($call->name->getLast());
            return isset($funcs[$k]) ? [$k] : [];
        }
        if ($call instanceof Expr\New_ && $call->class instanceof Node\Name) {
            $k = 'm:' . strtolower($call->class->getLast()) . '::__construct';
            return isset($funcs[$k]) ? [$k] : [];
        }
        if (($call instanceof Expr\MethodCall || $call instanceof Expr\StaticCall || $call instanceof Expr\NullsafeMethodCall)
            && $call->name instanceof Node\Identifier) {
            return array_slice($methodsByName[strtolower($call->name->toString())] ?? [], 0, 3);
        }
        return [];
    };
    $lowerFunc = function ($k) use ($g, &$funcs, &$lowered, &$queue) {
        if (!isset($lowered[$k])) {
            $sn = [];
            $lowered[$k] = lower_cfg($g, $funcs[$k]->Body, $sn);
            foreach ($sn as $x) $queue[] = $x;
        }
        return $lowered[$k];
    };
    while ($qi < count($queue) && !$g->truncated) {
        $nid = $queue[$qi++];
        $ast = $g->nodes[$nid]['ast'];
        foreach ($callFinder($ast) as $call) {
            foreach ($resolve($call) as $k) {
                [$ce, $cx] = $lowerFunc($k);
                $g->edge($nid, $ce);          // call edge
                $g->edge($cx, $nid);          // return edge
            }
        }
    }
    // (D3) functions/methods/closures never reached from the main body
    foreach (array_keys($funcs) as $k) {
        if ($g->truncated) break;
        if (!isset($lowered[$k])) {
            $lowerFunc($k);
            while ($qi < count($queue) && !$g->truncated) {
                $nid = $queue[$qi++];
                foreach ($callFinder($g->nodes[$nid]['ast']) as $call)
                    foreach ($resolve($call) as $k2) { [$ce, $cx] = $lowerFunc($k2); $g->edge($nid, $ce); $g->edge($cx, $nid); }
            }
        }
    }

    // pruning: drop dummy + meaningless nodes, bridge their predecessors to successors
    $pred = [];
    foreach ($g->succ as $a => $ss) foreach ($ss as $b => $_) $pred[$b][$a] = true;
    $nPruned = 0;
    foreach ($g->nodes as $id => $nd) {
        $drop = $nd['dummy'] || is_meaningless($nd['ast']);
        if (!$drop) continue;
        if (!$nd['dummy']) $nPruned++;
        $ps = array_keys($pred[$id] ?? []); $ss = array_keys($g->succ[$id]);
        foreach ($ps as $p) { unset($g->succ[$p][$id]); foreach ($ss as $s) if ($s !== $p && $s !== $id) { $g->succ[$p][$s] = true; $pred[$s][$p] = true; } }
        foreach ($ss as $s) unset($pred[$s][$id]);
        unset($g->succ[$id]); unset($pred[$id]);
        $g->nodes[$id]['gone'] = true;
    }

    // emit
    $printer = new PrettyPrinter\Standard();
    $remap = []; $nodesOut = [];
    foreach ($g->nodes as $id => $nd) {
        if (!empty($nd['gone'])) continue;
        $ast = $nd['ast'];
        $stripped = deep($ast);
        $ts = new NodeTraverser(); $ts->addVisitor(new BodyStripper()); $stripped = $ts->traverse([$stripped])[0];
        $raw = print_node($printer, $stripped);
        $tn = new NodeTraverser(); $tn->addVisitor(new Normalizer());
        $norm = print_node($printer, $tn->traverse([deep($stripped)])[0]);
        $remap[$id] = count($nodesOut);
        $nodesOut[] = [$norm, $raw, risk_of($ast)];
    }
    $edges = [];
    foreach ($g->succ as $a => $ss) {
        if (!isset($remap[$a])) continue;
        foreach ($ss as $b => $_) if (isset($remap[$b])) $edges[] = [$remap[$a], $remap[$b]];
    }
    return ['parse_error' => $parseErr, 'truncated' => $g->truncated, 'n_pruned' => $nPruned,
            'n_funcs' => count($funcs), 'nodes' => $nodesOut, 'edges' => $edges];
}

// ---------------- batch driver ----------------
pcntl_async_signals(true);
pcntl_signal(SIGALRM, function () { throw new \RuntimeException('timeout'); });
$list = file($argv[1], FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
$out = fopen($argv[2], 'w');
foreach ($list as $line) {
    [$sid, $path] = explode("\t", $line, 2);
    $t0 = microtime(true);
    $rec = ['id' => $sid];
    try {
        pcntl_alarm(FILE_TIMEOUT_S);
        $rec += extract_file($path);
        pcntl_alarm(0);
        $rec['ok'] = true;
    } catch (\Throwable $e) {
        pcntl_alarm(0);
        $rec['ok'] = false; $rec['err'] = substr(get_class($e) . ': ' . $e->getMessage(), 0, 200);
    }
    $rec['secs'] = round(microtime(true) - $t0, 4);
    $j = json_encode($rec, JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_SLASHES);
    fwrite($out, ($j === false ? json_encode(['id' => $sid, 'ok' => false, 'err' => 'json']) : $j) . "\n");
    gc_collect_cycles();
}
fclose($out);
}
