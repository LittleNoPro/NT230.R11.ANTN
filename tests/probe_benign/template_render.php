<?php
function render($tpl, array $vars) {
    extract($vars, EXTR_SKIP);
    ob_start();
    include __DIR__ . "/templates/$tpl.php";
    return ob_get_clean();
}
$products = [['name' => 'Pump A', 'price' => 120], ['name' => 'Valve B', 'price' => 45]];
echo render('list', ['title' => 'Products', 'items' => $products]);
