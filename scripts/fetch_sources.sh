#!/usr/bin/env bash
# Fetch raw corpora into samples/raw (git-ignored). Static analysis ONLY: never execute these files.
# Webshell repos are cloned with history (needed for first-commit dates / temporal split);
# large benign repos are shallow-cloned at a pinned tag.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$ROOT/samples/raw/webshell"; B="$ROOT/samples/raw/benign"
mkdir -p "$W" "$B"
clone() { # dir url [branch-or-tag] [depth]
  local d="$1" u="$2" br="${3:-}" dp="${4:-}"
  [ -d "$d/.git" ] && { echo "skip $d"; return; }
  local args=(-q -c core.autocrlf=false)
  [ -n "$br" ] && args+=(--branch "$br")
  [ -n "$dp" ] && args+=(--depth "$dp")
  git clone "${args[@]}" "$u" "$d" && echo "ok $d" || echo "FAIL $u"
}
# --- Webshell sources: paper Table 1 ---
clone "$W/Cyc1e183__PHP-Webshell-Dataset" https://github.com/Cyc1e183/PHP-Webshell-Dataset
clone "$W/bartblaze__PHP-backdoors"        https://github.com/bartblaze/PHP-backdoors
clone "$W/tennc__webshell"                 https://github.com/tennc/webshell
clone "$W/JohnTroony__php-webshells"       https://github.com/JohnTroony/php-webshells
clone "$W/ysrc__webshell-sample"           https://github.com/ysrc/webshell-sample
# --- Webshell sources: extension (held-out, dataset track) ---
clone "$W/BlackArch__webshells"            https://github.com/BlackArch/webshells
clone "$W/xl7dev__WebShell"                https://github.com/xl7dev/WebShell
# --- Benign sources: paper Table 1 (pinned tags) ---
clone "$B/WordPress__WordPress"  https://github.com/WordPress/WordPress 6.4.3 1
clone "$B/doorgets__CMS"         https://github.com/doorgets/CMS "" 1
clone "$B/laravel__laravel"      https://github.com/laravel/laravel v10.3.3 1
clone "$B/laravel__framework"    https://github.com/laravel/framework v10.48.4 1
clone "$B/PHPMailer__PHPMailer"  https://github.com/PHPMailer/PHPMailer v6.9.1 1
clone "$B/drupal__drupal"        https://github.com/drupal/drupal 10.2.5 1
# --- Benign sources: extension (held-out, dataset track) ---
clone "$B/phpmyadmin__phpmyadmin" https://github.com/phpmyadmin/phpmyadmin RELEASE_5_2_1 1
clone "$B/joomla__joomla-cms"     https://github.com/joomla/joomla-cms 5.0.3 1
clone "$B/matomo-org__matomo"     https://github.com/matomo-org/matomo 5.0.3 1
