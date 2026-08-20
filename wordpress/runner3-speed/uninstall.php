<?php
if (!defined('WP_UNINSTALL_PLUGIN')) exit;

$dropin = WP_CONTENT_DIR . '/advanced-cache.php';
if (is_file($dropin)) {
    $head = @file_get_contents($dropin, false, null, 0, 4096);
    if (is_string($head) && strpos($head, 'RUNNER3_SPEED_DROPIN') !== false) @unlink($dropin);
}

$cache = WP_CONTENT_DIR . '/cache/runner3-speed';
if (is_dir($cache)) {
    $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($cache, FilesystemIterator::SKIP_DOTS), RecursiveIteratorIterator::CHILD_FIRST);
    foreach ($it as $item) {
        if ($item->isDir()) @rmdir($item->getPathname()); else @unlink($item->getPathname());
    }
    @rmdir($cache);
}

foreach ([ABSPATH.'wp-config.php', dirname(ABSPATH).'/wp-config.php'] as $path) {
    if (!is_file($path) || !is_readable($path) || !is_writable($path)) continue;
    $text = @file_get_contents($path);
    if (!is_string($text) || strpos($text, 'RUNNER3_SPEED_WP_CACHE') === false) break;
    $rx = '/\/\*\s*RUNNER3_SPEED_WP_CACHE\s*\*\/\s*define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)\s*;\s*/i';
    $new = preg_replace($rx, '', $text, 1);
    if (is_string($new) && $new !== $text) {
        $tmp = dirname($path) . '/.runner3-uninstall-' . uniqid('', true) . '.tmp';
        if (@file_put_contents($tmp, $new, LOCK_EX) !== false) {
            $perms = @fileperms($path); if ($perms) @chmod($tmp, $perms & 0777);
            if (!@rename($tmp, $path)) @unlink($tmp);
        }
    }
    break;
}

delete_option('runner3_speed_enabled');
delete_option('runner3_speed_status');
delete_option('runner3_speed_critical_fonts');
