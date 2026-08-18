<?php
/**
 * Plugin Name: Runner5 Edge Optimizer
 * Description: Safe anonymous-public cache eligibility and conservative front-end script deferral for the Runner5 restore lab.
 * Version: 1.0.0
 * Author: Runner5 Restore Lab
 */

if (!defined('ABSPATH')) exit;

function runner5_edge_eligible() {
    if (is_admin() || wp_doing_ajax() || is_feed() || is_robots() || is_search() || is_404() || is_preview()) return false;
    if (defined('REST_REQUEST') && REST_REQUEST) return false;
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET') return false;
    if (is_user_logged_in()) return false;
    if (!empty($_SERVER['HTTP_COOKIE'])) return false;
    return is_front_page() || is_home() || is_singular() || is_archive();
}

function runner5_edge_start_buffer() {
    if (!runner5_edge_eligible()) return;
    @ini_set('zlib.output_compression', '0');
    header('Cache-Control: public, max-age=60, s-maxage=600, stale-while-revalidate=600, stale-if-error=3600', true);
    header('X-Runner5-Cache-Eligible: 1', true);
    header('X-Runner5-Origin-Stamp: ' . sprintf('%.6f', microtime(true)), true);
    header_remove('Pragma');
    ob_start(static function ($html) {
        if (!headers_sent()) {
            header_remove('Transfer-Encoding');
            header('Content-Length: ' . strlen($html), true);
        }
        return $html;
    });
}
add_action('template_redirect', 'runner5_edge_start_buffer', 0);

function runner5_edge_defer_known_scripts($tag, $handle, $src) {
    if (!is_string($tag) || stripos($tag, '<script') === false || preg_match('/\s(?:defer|async)(?:\s|=|>)/i', $tag)) return $tag;
    $src = (string) $src;
    $safe = array(
        '/wp-includes/js/jquery/jquery.min.js',
        '/wp-includes/js/jquery/jquery-migrate.min.js',
        '/wp-content/themes/inspiro/assets/js/',
        '/wp-includes/js/wp-emoji-release.min.js',
    );
    foreach ($safe as $fragment) {
        if (strpos($src, $fragment) !== false) return preg_replace('/<script\b/i', '<script defer', $tag, 1);
    }
    return $tag;
}
add_filter('script_loader_tag', 'runner5_edge_defer_known_scripts', 20, 3);

// Remove the legacy emoji discovery payload for modern browsers.
remove_action('wp_head', 'print_emoji_detection_script', 7);
remove_action('wp_print_styles', 'print_emoji_styles');
remove_action('admin_print_scripts', 'print_emoji_detection_script');
remove_action('admin_print_styles', 'print_emoji_styles');
