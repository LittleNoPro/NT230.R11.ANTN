<?php
session_start();
$pdo = new PDO('mysql:host=localhost;dbname=app', 'app', getenv('DB_PASS'));
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $stmt = $pdo->prepare('SELECT id, password_hash FROM users WHERE username = ?');
    $stmt->execute([$_POST['username'] ?? '']);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($user && password_verify($_POST['password'] ?? '', $user['password_hash'])) {
        session_regenerate_id(true);
        $_SESSION['uid'] = $user['id'];
        header('Location: dashboard.php');
        exit;
    }
    $error = 'Wrong username or password';
}
