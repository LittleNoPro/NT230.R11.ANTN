<?php
$file = __DIR__ . '/guestbook.txt';
if (!empty($_POST['msg'])) {
    $line = date('Y-m-d H:i') . "\t" . str_replace(["\t", "\n"], ' ', $_POST['name']) . "\t" . str_replace(["\t", "\n"], ' ', $_POST['msg']) . "\n";
    file_put_contents($file, $line, FILE_APPEND | LOCK_EX);
}
$entries = file_exists($file) ? array_reverse(file($file)) : [];
foreach (array_slice($entries, 0, 20) as $e) {
    [$when, $name, $msg] = explode("\t", rtrim($e));
    printf("<p><b>%s</b> (%s): %s</p>\n", htmlspecialchars($name), $when, htmlspecialchars($msg));
}
