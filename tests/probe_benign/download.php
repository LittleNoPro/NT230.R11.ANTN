<?php
$files = ['manual' => 'manual.pdf', 'brochure' => 'brochure.pdf', 'pricelist' => 'prices.xlsx'];
$key = $_GET['f'] ?? '';
if (!isset($files[$key])) {
    http_response_code(404);
    exit('Not found');
}
$path = __DIR__ . '/files/' . $files[$key];
header('Content-Type: application/octet-stream');
header('Content-Length: ' . filesize($path));
header('Content-Disposition: attachment; filename="' . basename($path) . '"');
readfile($path);
