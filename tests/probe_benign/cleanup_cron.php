<?php
// Run from cron: delete cache files older than 7 days.
$dir = __DIR__ . '/cache';
$limit = time() - 7 * 86400;
$removed = 0;
foreach (new DirectoryIterator($dir) as $f) {
    if ($f->isFile() && $f->getMTime() < $limit) {
        unlink($f->getPathname());
        $removed++;
    }
}
error_log("cleanup: removed $removed files");
