<?php
function greet($name) { return "Hello " . htmlspecialchars($name); }
echo greet($_GET["n"] ?? "world");
