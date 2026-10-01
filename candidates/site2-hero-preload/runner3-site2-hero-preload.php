<?php
/**
 * Plugin Name: Runner3 Site2 Hero Preload Candidate
 * Description: Candidate optimization for Site2: preload the diagnosed Organic Store CSS-background LCP resource so it is discovered from the HTML head.
 * Version: 1.0.1
 */

if (!defined('ABSPATH')) exit;

define('RUNNER3_SITE2_HERO_PRELOAD_VERSION', 'site2-organic-store-hero-preload-v1');

function runner3_site2_hero_preload_url() {
    if (!is_front_page()) return '';

    // Evidence-derived from the Site2 Organic Store diagnosis: this exact
    // background is the observed LCP resource. Do not infer it from raw
    // post_content because Spectra can materialize background CSS separately.
    $url = home_url('/wp-content/uploads/2020/09/leaves-bg.jpg');
    $home_host = wp_parse_url(home_url('/'), PHP_URL_HOST);
    $url_host = wp_parse_url($url, PHP_URL_HOST);
    if (!$home_host || !$url_host || strtolower($home_host) !== strtolower($url_host)) return '';
    return esc_url_raw($url);
}

add_action('wp_head', function () {
    $url = runner3_site2_hero_preload_url();
    if (!$url) return;
    printf(
        '<link id="runner3-site2-hero-preload" rel="preload" as="image" href="%s" fetchpriority="high">' . "\n",
        esc_url($url)
    );
}, 1);
