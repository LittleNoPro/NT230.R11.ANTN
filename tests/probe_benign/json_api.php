<?php
header('Content-Type: application/json');
$data = json_decode(file_get_contents('php://input'), true);
$action = $_GET['action'] ?? 'list';
$file = __DIR__ . '/data/todos.json';
$todos = file_exists($file) ? json_decode(file_get_contents($file), true) : [];
switch ($action) {
    case 'add':
        $todos[] = ['id' => count($todos) + 1, 'text' => substr($data['text'] ?? '', 0, 200), 'done' => false];
        break;
    case 'done':
        foreach ($todos as &$t) if ($t['id'] == ($data['id'] ?? 0)) $t['done'] = true;
        break;
}
file_put_contents($file, json_encode($todos));
echo json_encode($todos);
