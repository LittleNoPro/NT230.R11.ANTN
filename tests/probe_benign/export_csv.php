<?php
require 'db.php';
header('Content-Type: text/csv');
header('Content-Disposition: attachment; filename="orders.csv"');
$out = fopen('php://output', 'w');
fputcsv($out, ['id', 'customer', 'total', 'date']);
$from = $_GET['from'] ?? date('Y-m-01');
$stmt = $db->prepare('SELECT id, customer, total, created_at FROM orders WHERE created_at >= ?');
$stmt->execute([$from]);
while ($row = $stmt->fetch(PDO::FETCH_NUM)) {
    fputcsv($out, $row);
}
fclose($out);
