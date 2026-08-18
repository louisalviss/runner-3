<?php
/**
 * Plugin Name: Runner3 R2 Responsive Images
 * Description: Adds verified static R2 responsive variants to OFFSET frontend images without client-side JavaScript.
 * Version: 1.0.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) {
    exit;
}

const RUNNER3_R2_ORIGIN = 'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const RUNNER3_R2_SITE_PREFIX = '/sites/runner3-factory-smoke-2/';
const RUNNER3_R2_VARIANT_DIR = 'responsive-v2/';

function runner3_r2_candidate_srcset(string $stem): string {
    $base = RUNNER3_R2_ORIGIN . RUNNER3_R2_SITE_PREFIX . RUNNER3_R2_VARIANT_DIR . $stem;
    return $base . '-w360.webp 360w, ' . $base . '-w480.webp 480w, ' . $base . '-w640.webp 640w';
}

function runner3_r2_attr(string $tag, string $name): ?string {
    $pattern = '/\\b' . preg_quote($name, '/') . '\\s*=\\s*(["\\\'])(.*?)\\1/is';
    if (preg_match($pattern, $tag, $m)) {
        return html_entity_decode($m[2], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    }
    return null;
}

function runner3_r2_set_attr(string $tag, string $name, string $value): string {
    $escaped = esc_attr($value);
    $pattern = '/\\s+' . preg_quote($name, '/') . '\\s*=\\s*(["\\\']).*?\\1/is';
    if (preg_match($pattern, $tag)) {
        return preg_replace($pattern, ' ' . $name . '="' . $escaped . '"', $tag, 1) ?: $tag;
    }
    return preg_replace('/\\s*\\/?>(\\s*)$/', ' ' . $name . '="' . $escaped . '">$1', $tag, 1) ?: $tag;
}

function runner3_r2_rewrite_img(string $tag): string {
    $src = runner3_r2_attr($tag, 'src');
    if (!$src) {
        return $tag;
    }

    $origin = preg_quote(RUNNER3_R2_ORIGIN . RUNNER3_R2_SITE_PREFIX, '/');
    if (!preg_match('/^' . $origin . '(offset-demo-(0[1-8]))\\.webp(?:[?#].*)?$/i', $src, $m)) {
        return $tag;
    }

    $stem = strtolower($m[1]);
    $srcset = runner3_r2_candidate_srcset($stem);
    $tag = runner3_r2_set_attr($tag, 'srcset', $srcset);

    if (!runner3_r2_attr($tag, 'sizes')) {
        $tag = runner3_r2_set_attr($tag, 'sizes', '(max-width: 800px) 92vw, 46vw');
    }

    return $tag;
}

function runner3_r2_rewrite_preload(string $tag): string {
    $rel = strtolower((string) runner3_r2_attr($tag, 'rel'));
    $as = strtolower((string) runner3_r2_attr($tag, 'as'));
    $href = runner3_r2_attr($tag, 'href');
    if ($rel !== 'preload' || $as !== 'image' || !$href) {
        return $tag;
    }

    $hero = RUNNER3_R2_ORIGIN . RUNNER3_R2_SITE_PREFIX . 'offset-demo-01.webp';
    if (strtok($href, '?#') !== $hero) {
        return $tag;
    }

    $tag = runner3_r2_set_attr($tag, 'imagesrcset', runner3_r2_candidate_srcset('offset-demo-01'));
    $tag = runner3_r2_set_attr($tag, 'imagesizes', '(max-width: 767px) 80vw, 580px');
    return $tag;
}

function runner3_r2_optimize_html(string $html): string {
    if ($html === '' || stripos($html, '<html') === false) {
        return $html;
    }

    $html = preg_replace_callback('/<img\\b[^>]*>/is', static function ($m) {
        return runner3_r2_rewrite_img($m[0]);
    }, $html) ?: $html;

    $hero_preload_seen = false;
    $html = preg_replace_callback('/<link\\b[^>]*>/is', static function ($m) use (&$hero_preload_seen) {
        $rewritten = runner3_r2_rewrite_preload($m[0]);
        if ($rewritten !== $m[0]) {
            $hero_preload_seen = true;
        }
        return $rewritten;
    }, $html) ?: $html;

    if (!$hero_preload_seen && stripos($html, '</head>') !== false) {
        $hero = RUNNER3_R2_ORIGIN . RUNNER3_R2_SITE_PREFIX . 'offset-demo-01.webp';
        $preload = '<link rel="preload" as="image" href="' . esc_url($hero) . '" imagesrcset="' . esc_attr(runner3_r2_candidate_srcset('offset-demo-01')) . '" imagesizes="(max-width: 767px) 80vw, 580px">';
        $html = preg_replace('/<\\/head>/i', $preload . "\n</head>", $html, 1) ?: $html;
    }

    return $html;
}

function runner3_r2_start_buffer(): void {
    if (is_admin() || wp_doing_ajax() || is_feed() || is_robots() || (defined('REST_REQUEST') && REST_REQUEST)) {
        return;
    }
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET') {
        return;
    }
    ob_start('runner3_r2_optimize_html');
}
add_action('template_redirect', 'runner3_r2_start_buffer', 0);

function runner3_r2_resource_hints(array $urls, string $relation_type): array {
    if ($relation_type === 'preconnect' || $relation_type === 'dns-prefetch') {
        $urls[] = RUNNER3_R2_ORIGIN;
    }
    return array_values(array_unique($urls, SORT_REGULAR));
}
add_filter('wp_resource_hints', 'runner3_r2_resource_hints', 10, 2);
