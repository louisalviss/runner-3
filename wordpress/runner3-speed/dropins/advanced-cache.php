<?php
/* RUNNER3_SPEED_DROPIN v1.2.0 */
if (!defined('ABSPATH')) return;

$runner3_expected_version = '1.2.0';
$runner3_cache_key_version = 'v120';
$runner3_plugin = __DIR__ . '/plugins/runner3-speed/runner3-speed.php';
if (!is_file($runner3_plugin)) return;

$runner3_dir = __DIR__ . '/cache/runner3-speed';
$runner3_flag = $runner3_dir . '/enabled.flag';
if (!is_file($runner3_flag)) return;
$runner3_flag_version = trim((string)@file_get_contents($runner3_flag, false, null, 0, 64));
if ($runner3_flag_version !== $runner3_expected_version) {
    if (!headers_sent()) {
        header('X-Runner3-Speed: BYPASS-VERSION');
        header('X-Runner3-Speed-Version: '.$runner3_expected_version);
    }
    return;
}

$runner3_method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
if ($runner3_method !== 'GET' && $runner3_method !== 'HEAD') return;
if (!empty($_SERVER['QUERY_STRING'])) return;

$runner3_uri = (string)($_SERVER['REQUEST_URI'] ?? '/');
$runner3_path = parse_url($runner3_uri, PHP_URL_PATH) ?: '/';
if (preg_match('#^/(?:wp-admin(?:/|$)|wp-login\.php(?:/|$)|wp-json(?:/|$)|xmlrpc\.php$|wp-cron\.php$|cart(?:/|$)|checkout(?:/|$)|my-account(?:/|$)|wc-api(?:/|$))#i', $runner3_path)) return;

foreach (array_keys($_COOKIE ?? []) as $runner3_cookie) {
    if (preg_match('/^(wordpress_logged_in_|wordpress_sec_|wp-postpass_|woocommerce_items_in_cart$|woocommerce_cart_hash$|wp_woocommerce_session_|comment_author_)/i', (string)$runner3_cookie)) return;
}

$runner3_host = strtolower((string)($_SERVER['HTTP_HOST'] ?? ''));
if ($runner3_host === '') return;
$runner3_file = $runner3_dir . '/pages/' . hash('sha256', $runner3_cache_key_version . "\n" . $runner3_host . "\n" . $runner3_path) . '.html';

if (!is_file($runner3_file)) {
    if (!headers_sent()) {
        header('X-Runner3-Speed: MISS');
        header('X-Runner3-Speed-Version: '.$runner3_expected_version);
    }
    return;
}

$runner3_mtime = @filemtime($runner3_file);
$runner3_size = @filesize($runner3_file);
$runner3_head = @file_get_contents($runner3_file, false, null, 0, 4096);
if (!$runner3_mtime || (time() - $runner3_mtime) > 3600 || $runner3_size === false || $runner3_size < 512 || !is_string($runner3_head) || stripos($runner3_head, '<html') === false) {
    @unlink($runner3_file);
    if (!headers_sent()) {
        header('X-Runner3-Speed: MISS');
        header('X-Runner3-Speed-Version: '.$runner3_expected_version);
    }
    return;
}

if (!headers_sent()) {
    header('Content-Type: text/html; charset=UTF-8');
    header('Cache-Control: no-cache, must-revalidate, max-age=0');
    header('Expires: Wed, 11 Jan 1984 05:00:00 GMT');
    if ($runner3_size !== false) header('Content-Length: '.(string)$runner3_size);
    header('X-Runner3-Speed: HIT');
    header('X-Runner3-Speed-Version: '.$runner3_expected_version);
}
if ($runner3_method === 'HEAD') exit;
readfile($runner3_file);
exit;
