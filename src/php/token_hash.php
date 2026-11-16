<?php
// Lex only: never include, evaluate or execute input files. Keep literal bytes intact.
$paths = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
$out = [];
foreach ($paths as $path) {
    $hash = hash_init('sha256');
    $code = file_get_contents($path);
    if ($code === false) throw new RuntimeException('Cannot read sample');
    foreach (token_get_all($code) as $token) {
        if (is_array($token)) {
            [$kind, $value] = $token;
            if ($kind === T_WHITESPACE) continue;
            // Token names are stable across PHP token-number changes.
            $kind = token_name($kind);
        } else { $kind = 'CHAR'; $value = $token; }
        hash_update($hash, $kind . ':' . strlen($value) . ':' . $value);
    }
    $out[] = hash_final($hash);
}
echo json_encode($out, JSON_THROW_ON_ERROR), "\n";
