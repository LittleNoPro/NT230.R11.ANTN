<?php
$routes = [
    '/' => 'pages/home.php',
    '/about' => 'pages/about.php',
    '/products' => 'pages/products.php',
];
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (isset($routes[$path])) {
    include __DIR__ . '/' . $routes[$path];
} else {
    http_response_code(404);
    include __DIR__ . '/pages/404.php';
}
