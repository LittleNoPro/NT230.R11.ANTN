<?php
// Internal network diagnostics page for the admin panel.
require 'auth.php';
$host = $_POST['host'] ?? '';
if ($host !== '' && filter_var($host, FILTER_VALIDATE_IP)) {
    $output = shell_exec('ping -c 3 ' . escapeshellarg($host));
    echo '<pre>' . htmlspecialchars($output) . '</pre>';
}
