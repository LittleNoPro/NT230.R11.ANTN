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

# --- Small benign applications: improvement experiment (src/hard_benign.py), pinned commits ---
S="$ROOT/samples/raw/benign_small"; mkdir -p "$S"
clone_rev() { # dir url commit  (shallow fetch of one exact commit)
  local d="$1" u="$2" c="$3"
  [ -d "$d/.git" ] && { echo "skip $d"; return; }
  git init -q "$d" && git -C "$d" fetch -q --depth 1 "$u" "$c" && git -C "$d" checkout -q FETCH_HEAD && echo "ok $d" || echo "FAIL $u"
}
clone_rev "$S/Cacti__cacti" https://github.com/Cacti/cacti 8f4ac605b2ca405876554bb081027b5a8ede6d1e
clone_rev "$S/YOURLS__YOURLS" https://github.com/YOURLS/YOURLS dc76086a4c1bbe48f428e5f627c81c9bda409025
clone_rev "$S/fluxbb__fluxbb" https://github.com/fluxbb/fluxbb 5a2f95a34ef426f2b12103a32d5d4ba24a14391a
clone_rev "$S/mybb__mybb" https://github.com/mybb/mybb b47ea96cab426ae9ab53e7749cc3a3ea45e7d949
clone_rev "$S/opnsense__core" https://github.com/opnsense/core bc49b61db6d18be5805bcfcfbad558e4c7819f36
clone_rev "$S/osTicket__osTicket" https://github.com/osTicket/osTicket 8d38b0619649a50ee7cbbf37085f5d297fdc6f36
clone_rev "$S/prasathmani__tinyfilemanager" https://github.com/prasathmani/tinyfilemanager 41491439a6b243c55502581e53fad20bc4c6e777
clone_rev "$S/splitbrain__dokuwiki" https://github.com/splitbrain/dokuwiki ab1349690553fb0c339a042c6b4e12c7607334c4
clone_rev "$S/vrana__adminer" https://github.com/vrana/adminer 6f72c777f189290caf45521b2260190fd8f4ff2f
