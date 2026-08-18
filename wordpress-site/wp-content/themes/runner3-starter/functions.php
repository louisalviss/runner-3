<?php
if (!defined('ABSPATH')) exit;

function runner3_editorial_setup() {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form','gallery','caption','style','script']);
    register_nav_menus(['primary' => __('Primary Menu', 'runner3-starter')]);
}
add_action('after_setup_theme', 'runner3_editorial_setup');

/**
 * Mark only anonymous, public HTML as shared-cacheable.
 *
 * Wasmer CDN Cache is app-wide, so the response must opt in safely. Authenticated,
 * admin, REST, search, feed, preview and error responses remain dynamic/bypassed.
 * Browser freshness stays at zero while the shared edge may retain HTML briefly.
 */
function runner3_public_edge_cache_eligible() {
    $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
    if (!in_array($method, ['GET', 'HEAD'], true)) return false;
    if (is_admin() || is_user_logged_in()) return false;
    if (defined('REST_REQUEST') && REST_REQUEST) return false;
    if (defined('XMLRPC_REQUEST') && XMLRPC_REQUEST) return false;
    if (is_preview() || is_search() || is_feed() || is_trackback() || is_404()) return false;
    if (isset($_GET['preview']) || isset($_GET['preview_id']) || isset($_GET['rest_route']) || isset($_GET['s'])) return false;
    return true;
}

function runner3_public_edge_cache_headers() {
    if (!runner3_public_edge_cache_eligible()) return;

    // Shared edge cache: 5 minutes. Browsers revalidate normally, so editorial
    // updates do not get trapped in a long local cache on the visitor's device.
    header_remove('Pragma');
    header_remove('Expires');
    header('Cache-Control: public, max-age=0, s-maxage=300, stale-while-revalidate=60, stale-if-error=600', true);
    header('X-Runner3-Edge-Cache: public', true);
}
add_action('template_redirect', 'runner3_public_edge_cache_headers', 999);

function runner3_front_cleanup() {
    // OFFSET does not use emoji rendering or embeds on the homepage. Removing these
    // WordPress compatibility assets cuts parser/main-thread work without changing UI.
    remove_action('wp_head', 'print_emoji_detection_script', 7);
    remove_action('wp_print_styles', 'print_emoji_styles');
    remove_action('wp_enqueue_scripts', 'wp_enqueue_emoji_styles');
}
add_action('init', 'runner3_front_cleanup');

function runner3_editorial_assets() {
    $style_path = get_stylesheet_directory() . '/style.css';
    $version = file_exists($style_path) ? (string) filemtime($style_path) : '2.5.0';

    if (!is_front_page()) {
        wp_enqueue_style('runner3-editorial', get_stylesheet_uri(), [], $version);
        return;
    }

    // Homepage CSS and motion are inlined below: no blocking stylesheet request and
    // no extra script round-trip. wp-embed is not used by this custom front template.
    wp_dequeue_script('wp-embed');
}
add_action('wp_enqueue_scripts', 'runner3_editorial_assets', 100);

function runner3_front_critical_css() {
    if (!is_front_page()) return;
    $files = [
        get_stylesheet_directory() . '/style.css',
        get_stylesheet_directory() . '/home.css',
    ];
    $css = '';
    foreach ($files as $file) {
        if (is_readable($file)) $css .= "\n" . file_get_contents($file);
    }
    if ($css !== '') echo "<style id=\"runner3-critical-css\">" . $css . "</style>\n";
}
add_action('wp_head', 'runner3_front_critical_css', 5);

function runner3_front_motion_script() {
    if (!is_front_page()) return;
    $file = get_stylesheet_directory() . '/motion.js';
    if (!is_readable($file)) return;
    echo "\n<script id=\"runner3-motion-inline\">" . file_get_contents($file) . "</script>\n";
}
add_action('wp_footer', 'runner3_front_motion_script', 20);

function runner3_front_meta_description() {
    if (!is_front_page()) return;
    $description = get_bloginfo('description') ?: 'Technology, culture and the systems underneath.';
    echo '<meta name="description" content="' . esc_attr(wp_strip_all_tags($description)) . '">' . "\n";
}
add_action('wp_head', 'runner3_front_meta_description', 4);

function runner3_demo_images() {
    return [
        'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1523726491678-bf852e717f6a?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1484417894907-623942c8ee29?auto=format&fit=crop&w=1800&q=82'
    ];
}

function runner3_media_fallback_ids() {
    static $ids = null;
    if ($ids !== null) return $ids;

    $ids = get_posts([
        'post_type' => 'attachment',
        'post_mime_type' => 'image',
        'post_status' => 'inherit',
        'posts_per_page' => 8,
        'orderby' => 'date',
        'order' => 'DESC',
        'fields' => 'ids',
        'no_found_rows' => true,
    ]);
    $ids = array_values(array_filter(array_map('absint', is_array($ids) ? $ids : [])));
    return $ids;
}

function runner3_story_attachment_id($post_id = 0, $offset = 0) {
    $post_id = $post_id ?: get_the_ID();
    if ($post_id) {
        $featured = get_post_thumbnail_id($post_id);
        if ($featured) return absint($featured);
    }

    // New/automated posts may arrive before their own featured image. Reuse an
    // existing Media Library attachment (offloaded by Runner3 R2 Media) instead of
    // hotlinking a third-party image. This keeps the frontend R2-first and reliable.
    $fallbacks = runner3_media_fallback_ids();
    if (!$fallbacks) return 0;
    return $fallbacks[(absint($post_id) + absint($offset)) % count($fallbacks)];
}

function runner3_story_image($post_id = 0, $offset = 0) {
    $post_id = $post_id ?: get_the_ID();
    $attachment_id = runner3_story_attachment_id($post_id, $offset);
    if ($attachment_id) {
        $url = wp_get_attachment_image_url($attachment_id, 'large');
        if ($url) return $url;
    }
    $images = runner3_demo_images();
    return $images[(absint($post_id) + absint($offset)) % count($images)];
}

function runner3_is_unsplash_image($url) {
    return is_string($url) && strpos($url, 'https://images.unsplash.com/') === 0;
}

function runner3_unsplash_variant($url, $width, $quality = 76) {
    if (!runner3_is_unsplash_image($url)) return $url;
    return add_query_arg([
        'auto' => 'format',
        'fit' => 'crop',
        'w' => absint($width),
        'q' => absint($quality),
    ], $url);
}

function runner3_unsplash_srcset($url) {
    if (!runner3_is_unsplash_image($url)) return '';
    $widths = [480, 640, 800, 960, 1200, 1600];
    $parts = [];
    foreach ($widths as $width) {
        $parts[] = esc_url(runner3_unsplash_variant($url, $width)) . ' ' . $width . 'w';
    }
    return implode(', ', $parts);
}

function runner3_story_image_html($post_id = 0, $attributes = []) {
    $post_id = $post_id ?: get_the_ID();
    $attachment_id = runner3_story_attachment_id($post_id);
    $defaults = [
        'alt' => $post_id ? get_the_title($post_id) : '',
        'decoding' => 'async',
        'sizes' => '(max-width: 767px) 92vw, 1100px',
    ];
    $attributes = array_merge($defaults, $attributes);

    if ($attachment_id) {
        // WordPress emits responsive markup while Runner3 R2 Media rewrites the
        // attachment URL to remote storage.
        return wp_get_attachment_image($attachment_id, 'large', false, $attributes);
    }

    $original = runner3_story_image($post_id);
    $src = runner3_is_unsplash_image($original) ? runner3_unsplash_variant($original, 960) : $original;
    if (runner3_is_unsplash_image($original) && empty($attributes['srcset'])) {
        $attributes['srcset'] = runner3_unsplash_srcset($original);
    }

    $attr_html = '';
    foreach ($attributes as $key => $value) {
        if ($value === false || $value === null || $value === '') continue;
        $attr_html .= ' ' . esc_attr($key) . '="' . esc_attr($value) . '"';
    }
    return '<img src="' . esc_url($src) . '"' . $attr_html . '>';
}

function runner3_preload_front_lcp() {
    if (!is_front_page()) return;
    $latest = get_posts(['numberposts' => 1, 'post_status' => 'publish', 'fields' => 'ids']);
    if (!$latest) return;

    $src = runner3_story_image((int) $latest[0]);
    if (!$src) return;

    $sizes = '(max-width: 767px) 80vw, 580px';
    if (runner3_is_unsplash_image($src)) {
        $href = runner3_unsplash_variant($src, 960);
        $srcset = runner3_unsplash_srcset($src);
        echo '<link rel="preload" as="image" href="' . esc_url($href) . '" imagesrcset="' . esc_attr($srcset) . '" imagesizes="' . esc_attr($sizes) . '" fetchpriority="high">' . "\n";
        return;
    }

    echo '<link rel="preload" as="image" href="' . esc_url($src) . '" fetchpriority="high">' . "\n";
}
add_action('wp_head', 'runner3_preload_front_lcp', 3);

function runner3_primary_fallback() {
    echo '<ul>';
    echo '<li><a href="' . esc_url(home_url('/#latest')) . '">Latest</a></li>';
    foreach (get_categories(['number' => 3, 'orderby' => 'count', 'order' => 'DESC']) as $cat) {
        echo '<li><a href="' . esc_url(get_category_link($cat)) . '">' . esc_html($cat->name) . '</a></li>';
    }
    $about = get_page_by_path('about');
    if ($about) echo '<li><a href="' . esc_url(get_permalink($about)) . '">About</a></li>';
    echo '</ul>';
}

function runner3_read_time($post_id = 0) {
    $post_id = $post_id ?: get_the_ID();
    $words = str_word_count(wp_strip_all_tags(get_post_field('post_content', $post_id)));
    return max(1, (int) ceil($words / 220));
}
