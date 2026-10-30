<?php
$errors = [];
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $name = trim($_POST['name'] ?? '');
    $email = filter_var($_POST['email'] ?? '', FILTER_VALIDATE_EMAIL);
    $msg = trim($_POST['message'] ?? '');
    if ($name === '') $errors[] = 'Name is required';
    if (!$email) $errors[] = 'Invalid email';
    if (strlen($msg) < 10) $errors[] = 'Message too short';
    if (!$errors) {
        mail('admin@example.com', 'Contact from ' . $name, $msg, 'Reply-To: ' . $email);
        header('Location: thanks.html');
        exit;
    }
}
?>
<form method="post">
  <?php foreach ($errors as $e) echo '<p class="err">' . htmlspecialchars($e) . '</p>'; ?>
  <input name="name"> <input name="email"> <textarea name="message"></textarea>
  <button>Send</button>
</form>
