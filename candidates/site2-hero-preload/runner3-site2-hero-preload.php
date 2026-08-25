<?php
/**
 * Plugin Name: Runner3 Site2 Hero Preload Candidate
 * Description: Candidate optimization for Site2: preload the first front-page background image so the CSS LCP resource is discovered earlier.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

define('RUNNER3_SITE2_HERO_PRELOAD_VERSION', 'site2-hero-preload-v1');

function runner3_site2_hero_preload_url() {
    if (!is_front_page()) return '';
    $front_id = (int) get_option('page_on_front');
    if (!$front_id) return '';
    $content = (string) get_post_field('post_content', $front_id);
    if (!$content) return '';

    if (!preg_match('/url\(\s*["\']?([^"\')]+)["\']?\s*\)/i', $content, $match)) return '';
    $url = esc_url_raw($match[1]);
    if (!$url) return '';

    $home_host = wp_parse_url(home_url('/'), PHP_URL_HOST);
    $url_host = wp_parse_url($url, PHP_URL_HOST);
    if (!$home_host || !$url_host || strtolower($home_host) !== strtolower($url_host)) return '';
    return $url;
}

add_action('wp_head', function () {
    $url = runner3_site2_hero_preload_url();
    if (!$url) return;
    printf(
        '<link id="runner3-site2-hero-preload" rel="preload" as="image" href="%s" fetchpriority="high">' . "\n",
        esc_url($url)
    );
}, 1);
