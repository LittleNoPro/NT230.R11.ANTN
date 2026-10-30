<?php
$allowed = ['image/jpeg' => 'jpg', 'image/png' => 'png'];
if (isset($_FILES['photo']) && $_FILES['photo']['error'] === UPLOAD_ERR_OK) {
    $finfo = new finfo(FILEINFO_MIME_TYPE);
    $mime = $finfo->file($_FILES['photo']['tmp_name']);
    if (!isset($allowed[$mime]) || $_FILES['photo']['size'] > 2 * 1024 * 1024) {
        http_response_code(400);
        die('Only JPEG/PNG up to 2 MB');
    }
    $name = bin2hex(random_bytes(8)) . '.' . $allowed[$mime];
    move_uploaded_file($_FILES['photo']['tmp_name'], __DIR__ . '/uploads/' . $name);
    echo 'Saved as ' . $name;
}
