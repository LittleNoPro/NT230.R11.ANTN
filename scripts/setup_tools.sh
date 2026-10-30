#!/usr/bin/env bash
# Fetch the static-analysis tooling at pinned commits (no composer needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/tools" && cd "$ROOT/tools"
[ -d LChecker ] || git clone -q https://github.com/cuhk-seclab/LChecker
git -C LChecker checkout -q c8a3646872a937024c3dd3f1dbe346832f55ef62
[ -d vendor/PHP-Parser ] || git clone -q --branch v4.19.4 https://github.com/nikic/PHP-Parser vendor/PHP-Parser
mkdir -p LChecker/src/vendor
cat > LChecker/src/vendor/autoload.php <<'PHP'
<?php
// Minimal PSR-4 autoloader replacing composer (nikic/php-parser v4.19.4 vendored from git)
spl_autoload_register(function ($c) {
    if (strpos($c, 'PhpParser\\') === 0) {
        $f = __DIR__ . '/../../../vendor/PHP-Parser/lib/' . str_replace('\\', '/', $c) . '.php';
        if (is_file($f)) require $f;
    }
});
PHP
echo "tools ready"
